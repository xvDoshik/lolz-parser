from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from playwright.async_api import async_playwright

from market_listing import parse_listing_rows
from skins_db import SKIN_TRANSPORT_ERR_MARKERS, init_sqlite, upsert_skin_rows

ROOT = Path(__file__).resolve().parent
CHECKPOINT_FILE = ROOT / ".crawl_resume.json"
_log = logging.getLogger("sonicparser.crawl")


def read_resume_index() -> int:
    try:
        data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        return max(0, int(data["next"]))
    except (OSError, ValueError, TypeError, KeyError):
        return 0


def write_resume_index(next_index: int) -> None:
    CHECKPOINT_FILE.write_text(
        json.dumps({"next": max(0, int(next_index))}, indent=2),
        encoding="utf-8",
    )


def _advance_resume_after_url(i: int, n: int) -> None:
    if i + 1 >= n:
        write_resume_index(0)
    else:
        write_resume_index(i + 1)


_RECOVERABLE_BROWSER_ERR_MARKERS: tuple[str, ...] = SKIN_TRANSPORT_ERR_MARKERS

MAX_BROWSER_RESTARTS_PER_URL = 3


def _is_recoverable_browser_transport_error(message: str | None) -> bool:
    if not message:
        return False
    return any(m in message for m in _RECOVERABLE_BROWSER_ERR_MARKERS)


async def _safe_close_browser_stack(
    page,
    context,
    browser,
) -> None:
    if page is not None:
        try:
            await page.close()
        except BaseException as ex:
            _log.info("page.close: %s", ex)
    if context is not None:
        try:
            await context.close()
        except BaseException as ex:
            _log.info("context.close: %s", ex)
    if browser is not None:
        try:
            await browser.close()
        except BaseException as ex:
            _log.info("browser.close: %s", ex)


async def _launch_browser_context_page(pw):
    browser = await pw.chromium.launch(headless=True)
    _log.info("browser launched")
    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        locale="ru-RU",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    return browser, context, page


_log_init = False


def _setup_crawl_logging() -> None:
    global _log_init
    if _log_init:
        return
    _log_init = True
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(
        logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S")
    )
    _log.addHandler(h)
    _log.setLevel(logging.INFO)
    _log.propagate = False


URLS_FILE = ROOT / "brawl-stars-skin-urls.txt"
DB_PATH = ROOT / "skins.sqlite"
SKINS_HTML_DIR = ROOT / "pages" / "skins"
NETWORKIDLE_TIMEOUT_MS = 12_000


async def _await_task_quiet(task: asyncio.Task) -> None:
    try:
        await task
    except BaseException:
        pass


async def _finish_task_pair(idle_task: asyncio.Task, stop_task: asyncio.Task) -> None:
    for t in (idle_task, stop_task):
        if not t.done():
            t.cancel()
    await _await_task_quiet(idle_task)
    await _await_task_quiet(stop_task)


async def _wait_networkidle_with_stop(
    page,
    stop_event: asyncio.Event,
    timeout_ms: int,
) -> None:
    idle_task = asyncio.create_task(
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    )
    stop_task = asyncio.create_task(stop_event.wait())
    try:
        done, _ = await asyncio.wait(
            {idle_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done and stop_event.is_set():
            raise asyncio.CancelledError()
        await idle_task
    finally:
        await _finish_task_pair(idle_task, stop_task)


def skin_slug_from_url(url: str) -> str:
    for k, v in parse_qsl(urlparse(url).query, keep_blank_values=True):
        if k == "skin[]":
            s = re.sub(r"[^\w\-.]", "_", v)
            return (s[:180] or "skin").strip("_") or "skin"
    path = urlparse(url).path or "/index"
    base = re.sub(r"/+", "-", path.strip("/")) or "index"
    return base[:80]


def skin_name_from_url(url: str) -> str:
    for k, v in parse_qsl(urlparse(url).query, keep_blank_values=True):
        if k == "skin[]":
            return v
    path = urlparse(url).path or "/index"
    return re.sub(r"/+", "-", path.strip("/"))[:120] or "index"


def read_urls(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


async def _sleep_coop(seconds: float, stop_event: asyncio.Event | None) -> None:
    end = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < end:
        if stop_event and stop_event.is_set():
            raise asyncio.CancelledError()
        slice_s = min(0.25, end - time.monotonic())
        if slice_s <= 0:
            break
        await asyncio.sleep(slice_s)


async def scroll_to_bottom(
    page,
    pause_ms: float = 0.6,
    stable_needed: int = 4,
    stop_event: asyncio.Event | None = None,
) -> None:
    t0 = time.monotonic()
    last_h = 0
    stable = 0
    rounds = 0
    while stable < stable_needed:
        rounds += 1
        height = await page.evaluate(
            """() => {
                window.scrollTo(0, document.documentElement.scrollHeight);
                return document.documentElement.scrollHeight;
            }"""
        )
        await _sleep_coop(pause_ms, stop_event)
        if height == last_h:
            stable += 1
        else:
            stable = 0
            last_h = height

    await page.evaluate(
        "window.scrollTo(0, document.documentElement.scrollHeight)"
    )
    await _sleep_coop(pause_ms, stop_event)
    _log.info(
        "scroll_to_bottom done rounds=%s last_h=%s elapsed=%.1fs",
        rounds,
        last_h,
        time.monotonic() - t0,
    )


async def fetch_one_html(
    page,
    url: str,
    stop_event: asyncio.Event | None = None,
) -> tuple[str | None, str | None]:
    t_all = time.monotonic()
    _log.info("fetch start url=%s", url[:120])
    if stop_event and stop_event.is_set():
        raise asyncio.CancelledError()
    try:
        t = time.monotonic()
        await page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        _log.info("after goto(domcontentloaded) %.1fs", time.monotonic() - t)
        if stop_event and stop_event.is_set():
            raise asyncio.CancelledError()

        t = time.monotonic()
        _log.info(
            "waiting networkidle (best-effort, max %s ms)…",
            NETWORKIDLE_TIMEOUT_MS,
        )
        try:
            if stop_event is not None:
                await _wait_networkidle_with_stop(
                    page, stop_event, NETWORKIDLE_TIMEOUT_MS
                )
            else:
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=NETWORKIDLE_TIMEOUT_MS
                    )
                except Exception:
                    pass
            _log.info("after networkidle ok %.1fs", time.monotonic() - t)
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            _log.info(
                "after networkidle timeout/skip %.1fs: %s",
                time.monotonic() - t,
                ex,
            )

        if stop_event and stop_event.is_set():
            raise asyncio.CancelledError()

        t = time.monotonic()
        await scroll_to_bottom(page, stop_event=stop_event)
        _log.info("after scroll block %.1fs", time.monotonic() - t)

        if stop_event and stop_event.is_set():
            raise asyncio.CancelledError()

        t = time.monotonic()
        html = await page.content()
        _log.info(
            "after page.content len=%s bytes %.1fs | total_fetch=%.1fs",
            len(html),
            time.monotonic() - t,
            time.monotonic() - t_all,
        )
        return html, None
    except asyncio.CancelledError:
        raise
    except Exception as e:
        _log.warning(
            "fetch FAILED after %.1fs: %s",
            time.monotonic() - t_all,
            e,
        )
        return None, f"{url} :: {e}"


async def run_crawl(
    *,
    stop_event: asyncio.Event | None = None,
    continuous: bool = False,
    db_path: Path | None = None,
    urls_file: Path | None = None,
    skins_dir: Path | None = None,
    on_progress=None,
    progress: dict | None = None,
    resume_index: int | None = None,
) -> tuple[int, int]:
    _setup_crawl_logging()
    db_path = db_path or DB_PATH
    urls_file = urls_file or URLS_FILE
    skins_dir = skins_dir or SKINS_HTML_DIR
    urls = read_urls(urls_file)
    skins_dir.mkdir(parents=True, exist_ok=True)
    n = len(urls)
    if n == 0:
        write_resume_index(0)
        return 0, 0

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    init_sqlite(conn)
    conn.commit()

    ok = 0
    err_n = 0

    try:
        async with async_playwright() as pw:
            _log.info("playwright starting browser…")
            browser = context = page = None
            try:
                browser, context, page = await _launch_browser_context_page(pw)
                start_i = (
                    resume_index
                    if resume_index is not None
                    else read_resume_index()
                )
                if start_i < 0 or start_i >= n:
                    start_i = 0
                i = start_i
                transport_retries = 0
                _log.info(
                    "crawl resume 0-based=%s (1-based start %s/%s), continuous=%s",
                    start_i,
                    start_i + 1,
                    n,
                    continuous,
                )
                while True:
                    if stop_event and stop_event.is_set():
                        write_resume_index(i)
                        _log.info(
                            "stop_event (checkpoint next=%s, 1-based would be %s)",
                            i,
                            i + 1,
                        )
                        break
                    if i >= n:
                        if not continuous:
                            break
                        i = 0
                        write_resume_index(0)
                        _log.info("continuous crawl: wrapped to url 1/%s", n)
                        continue
                    url = urls[i]
                    skin = skin_name_from_url(url)
                    slug = skin_slug_from_url(url)
                    if progress is not None:
                        progress["index"] = i + 1
                        progress["total_urls"] = n
                        progress["current_skin"] = skin
                    _log.info(
                        "=== [%s/%s] skin=%r slug=%r ===",
                        i + 1,
                        n,
                        skin,
                        slug,
                    )
                    t_url = time.monotonic()
                    try:
                        html, err = await fetch_one_html(
                            page, url, stop_event=stop_event
                        )
                    except asyncio.CancelledError:
                        write_resume_index(i)
                        _log.info(
                            "crawl cancelled at skin=%r (checkpoint next=%s)",
                            skin,
                            i,
                        )
                        raise
                    if err and _is_recoverable_browser_transport_error(err):
                        if transport_retries >= MAX_BROWSER_RESTARTS_PER_URL:
                            _log.error(
                                "[%s/%s] transport errors exhausted (%s) skin=%s",
                                i + 1,
                                n,
                                MAX_BROWSER_RESTARTS_PER_URL,
                                skin,
                            )
                            upsert_skin_rows(conn, skin, url, None, err)
                            conn.commit()
                            err_n += 1
                            if on_progress:
                                on_progress(skin, False)
                            _advance_resume_after_url(i, n)
                            transport_retries = 0
                            i += 1
                            continue
                        transport_retries += 1
                        _log.warning(
                            "[%s/%s] recoverable browser error, restarting "
                            "chromium (%s/%s): %s",
                            i + 1,
                            n,
                            transport_retries,
                            MAX_BROWSER_RESTARTS_PER_URL,
                            err[:400],
                        )
                        await _safe_close_browser_stack(page, context, browser)
                        browser, context, page = await _launch_browser_context_page(
                            pw
                        )
                        continue
                    if err:
                        transport_retries = 0
                        _log.warning(
                            "[%s/%s] ERROR skin=%s after %.1fs -> sqlite err row",
                            i + 1,
                            n,
                            skin,
                            time.monotonic() - t_url,
                        )
                        upsert_skin_rows(conn, skin, url, None, err)
                        conn.commit()
                        err_n += 1
                        if on_progress:
                            on_progress(skin, False)
                        _advance_resume_after_url(i, n)
                        i += 1
                        continue
                    transport_retries = 0
                    ids, listing_rows = parse_listing_rows(html)
                    upsert_skin_rows(conn, skin, url, ids, None, listing_rows)
                    conn.commit()
                    _log.info(
                        "[%s/%s] sqlite committed skin=%s item_ids=%s",
                        i + 1,
                        n,
                        skin,
                        len(ids),
                    )
                    out_html = skins_dir / f"{slug}.html"
                    out_html.write_text(html, encoding="utf-8")
                    ok += 1
                    _log.info(
                        "[%s/%s] OK skin=%s wrote %s (loop %.1fs)",
                        i + 1,
                        n,
                        skin,
                        out_html.name,
                        time.monotonic() - t_url,
                    )
                    if on_progress:
                        on_progress(skin, True)
                    _advance_resume_after_url(i, n)
                    i += 1
            finally:
                _log.info("closing browser stack…")
                await _safe_close_browser_stack(page, context, browser)
                _log.info("browser stack closed")
    finally:
        conn.close()

    return ok, err_n


async def run_crawl_cli() -> None:
    urls = read_urls(URLS_FILE)
    print(len(urls), "URLs ->", DB_PATH, "+", SKINS_HTML_DIR)
    ok, err_n = await run_crawl()
    print("Done:", ok, "ok,", err_n, "errors")


if __name__ == "__main__":
    asyncio.run(run_crawl_cli())
