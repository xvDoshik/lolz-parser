from __future__ import annotations

import asyncio
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from auth_gate import (
    COOKIE_NAME,
    attach_refreshed_cookie,
    client_ip,
    gate_enabled,
    gate_middleware,
    gate_request_ok,
    ip_login_is_rate_limited,
    ip_login_note_failure,
    ip_login_note_success,
    not_found,
    verify_login_password,
)
from crawl_worker import (
    DB_PATH,
    SKINS_HTML_DIR,
    URLS_FILE,
    read_resume_index,
    read_urls,
    run_crawl,
)
from optimize_rank import compute_top_deals, compute_top_deals_for_required_skins
from skins_db import (
    clear_nonfatal_skin_errors,
    configure_connection as configure_skins_sqlite,
    init_sqlite as init_skins_sqlite,
)
from layout_norm import query_variants, skin_matches_filters
from notifications import (
    load_config_for_api,
    notification_background_loop,
    save_config_from_body_locked,
)
from sell_listing import build_sell_bundle

ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
GATE_LOGIN_HTML = ROOT / "gate_login.html"

_parse_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None
_parse_progress: dict = {}
_pars_start_lock = asyncio.Lock()
_notify_task: asyncio.Task | None = None
_notify_stop: asyncio.Event | None = None

_SQLITE_BUSY_TIMEOUT_SEC = 60.0

_db_snapshot_cache_payload: dict | None = None
_db_snapshot_cache_mono: float = 0.0
_db_snapshot_refresh_lock = asyncio.Lock()
_DB_SNAPSHOT_CACHE_SEC = 5.0


def _sync_pars_status_counts() -> tuple[int, int, int]:
    html_count = len(list(SKINS_HTML_DIR.glob("*.html")))
    try:
        total = len(read_urls(URLS_FILE))
    except OSError:
        total = 0
    db_rows = 0
    try:
        conn = sqlite3.connect(DB_PATH, timeout=_SQLITE_BUSY_TIMEOUT_SEC)
        try:
            row = conn.execute("SELECT COUNT(*) FROM skins").fetchone()
            db_rows = int(row[0]) if row else 0
        finally:
            conn.close()
    except OSError:
        pass
    return html_count, total, db_rows


def _sync_db_snapshot_payload() -> dict:
    conn = sqlite3.connect(DB_PATH, timeout=_SQLITE_BUSY_TIMEOUT_SEC)
    conn.row_factory = sqlite3.Row
    try:
        skins_cur = conn.execute(
            "SELECT skin_name, url, item_count, fetched_at, error "
            "FROM skins ORDER BY skin_name COLLATE NOCASE"
        )
        skins = [dict(r) for r in skins_cur.fetchall()]
        row = conn.execute("SELECT COUNT(*) FROM skin_items").fetchone()
        skin_items_total = int(row[0]) if row else 0
        lim = _SKIN_ITEMS_SNAPSHOT_LIMIT + 1
        items_cur = conn.execute(
            """
            SELECT si.skin_name, si.item_id,
                   s.brawl_level, s.trophies, s.brawlers, s.legendary,
                   s.hypercharges, s.price, s.currency
            FROM skin_items si
            LEFT JOIN item_brawl_stats s ON s.item_id = si.item_id
            ORDER BY si.skin_name COLLATE NOCASE, CAST(si.item_id AS INTEGER)
            LIMIT ?
            """,
            (lim,),
        )
        item_rows = items_cur.fetchall()
        truncated = len(item_rows) > _SKIN_ITEMS_SNAPSHOT_LIMIT
        item_rows = item_rows[:_SKIN_ITEMS_SNAPSHOT_LIMIT]
        skin_items = [
            {
                "skin_name": r["skin_name"],
                "item_id": r["item_id"],
                "brawl_level": r["brawl_level"],
                "trophies": r["trophies"],
                "brawlers": r["brawlers"],
                "legendary": r["legendary"],
                "hypercharges": r["hypercharges"],
                "price": r["price"],
                "currency": r["currency"],
            }
            for r in item_rows
        ]
    finally:
        conn.close()
    return {
        "skins": skins,
        "skin_items": skin_items,
        "skin_items_total": skin_items_total,
        "skin_items_truncated": truncated,
    }


def _sync_search_skins_rows() -> list[tuple[str, int]]:
    conn = sqlite3.connect(DB_PATH, timeout=_SQLITE_BUSY_TIMEOUT_SEC)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT skin_name, item_count FROM skins WHERE error IS NULL ORDER BY skin_name"
        )
        return [(str(r["skin_name"]), int(r["item_count"])) for r in cur.fetchall()]
    finally:
        conn.close()


def _sync_search_by_skins_items(skins: list[str]) -> dict:
    ph = ",".join("?" * len(skins))
    n = len(skins)
    conn = sqlite3.connect(DB_PATH, timeout=_SQLITE_BUSY_TIMEOUT_SEC)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            f"""
            SELECT si.item_id, si.skin_name
            FROM skin_items si
            INNER JOIN (
                SELECT item_id
                FROM skin_items
                WHERE skin_name IN ({ph})
                GROUP BY item_id
                HAVING COUNT(DISTINCT skin_name) = ?
            ) both ON si.item_id = both.item_id
            WHERE si.skin_name IN ({ph})
            ORDER BY CAST(si.item_id AS INTEGER), si.skin_name
            """,
            (*skins, n, *skins),
        )
        item_to_skins: dict[str, list[str]] = defaultdict(list)
        for row in cur.fetchall():
            item_to_skins[str(row["item_id"])].append(row["skin_name"])
        stats_map: dict[str, dict] = {}
        if item_to_skins:
            ids = list(item_to_skins.keys())
            ph2 = ",".join("?" * len(ids))
            cur2 = conn.execute(
                f"""
                SELECT item_id, brawl_level, trophies, brawlers, legendary,
                       hypercharges, price, currency
                FROM item_brawl_stats
                WHERE item_id IN ({ph2})
                """,
                ids,
            )
            for row in cur2.fetchall():
                iid = str(row["item_id"])
                stats_map[iid] = {
                    "brawl_level": row["brawl_level"],
                    "trophies": row["trophies"],
                    "brawlers": row["brawlers"],
                    "legendary": row["legendary"],
                    "hypercharges": row["hypercharges"],
                    "price": row["price"],
                    "currency": row["currency"],
                }
    finally:
        conn.close()
    items = []
    for item_id in sorted(item_to_skins.keys(), key=lambda x: int(x)):
        sks = sorted(set(item_to_skins[item_id]))
        st = stats_map.get(item_id, {})
        items.append(
            {
                "item_id": item_id,
                "url": f"https://lzt.market/{item_id}/",
                "skins": sks,
                "brawl_level": st.get("brawl_level"),
                "trophies": st.get("trophies"),
                "brawlers": st.get("brawlers"),
                "legendary": st.get("legendary"),
                "hypercharges": st.get("hypercharges"),
                "price": st.get("price"),
                "currency": st.get("currency"),
            }
        )
    return {"items": items}


def _sync_clear_nonfatal_skin_errors() -> int:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=_SQLITE_BUSY_TIMEOUT_SEC)
    try:
        configure_skins_sqlite(conn)
        n = clear_nonfatal_skin_errors(conn)
        conn.commit()
        return n
    finally:
        conn.close()


def _sync_sell_compose(ident: str) -> dict:
    conn = sqlite3.connect(DB_PATH, timeout=_SQLITE_BUSY_TIMEOUT_SEC)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT item_id, brawl_level, trophies, brawlers, legendary,
                   hypercharges, price, currency
            FROM item_brawl_stats
            WHERE item_id = ?
            """,
            (ident,),
        ).fetchone()
        cur = conn.execute(
            """
            SELECT DISTINCT skin_name FROM skin_items
            WHERE item_id = ?
            ORDER BY skin_name COLLATE NOCASE
            """,
            (ident,),
        )
        skins = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    stats = dict(row) if row else None
    if not stats and not skins:
        raise ValueError(
            "В локальной БД этого лота нет (нет статов и скинов по этому item_id)."
        )
    texts = build_sell_bundle(ident, stats, skins)
    return {
        "item_id": ident,
        "url": f"https://lzt.market/{ident}/",
        **texts,
    }


def _sync_search_by_item_skins(ident: str) -> list[str]:
    conn = sqlite3.connect(DB_PATH, timeout=_SQLITE_BUSY_TIMEOUT_SEC)
    try:
        cur = conn.execute(
            "SELECT DISTINCT skin_name FROM skin_items WHERE item_id = ? ORDER BY skin_name",
            (ident,),
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


_SKIN_ITEMS_SNAPSHOT_LIMIT = 15_000


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _notify_task, _notify_stop
    SKINS_HTML_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    init_skins_sqlite(conn)
    conn.commit()
    conn.close()
    _notify_stop = asyncio.Event()
    _notify_task = asyncio.create_task(notification_background_loop(_notify_stop))
    try:
        yield
    finally:
        if _notify_stop is not None:
            _notify_stop.set()
        t = _notify_task
        if t is not None:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            _notify_task = None
        _notify_stop = None


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/pars/status")
async def pars_status():
    running = _parse_task is not None and not _parse_task.done()
    cur_skin = _parse_progress.get("current_skin") if running else None
    cur_idx = int(_parse_progress.get("index") or 0)
    html_count, total, db_rows = await asyncio.to_thread(_sync_pars_status_counts)
    pct = (html_count / total * 100.0) if total else 0.0
    return {
        "running": running,
        "html_count": html_count,
        "total": total,
        "percent": round(pct, 2),
        "db_skins_rows": db_rows,
        "current_index": cur_idx,
        "current_skin": cur_skin,
    }


@app.post("/api/pars/start")
async def pars_start():
    global _parse_task, _stop_event
    async with _pars_start_lock:
        t_prev = _parse_task
        if t_prev is not None:
            if t_prev.done():
                _parse_task = None
            else:
                if _stop_event is not None:
                    _stop_event.set()
                t_prev.cancel()
                try:
                    await t_prev
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
                _parse_task = None

        _stop_event = asyncio.Event()

        async def runner() -> None:
            global _parse_progress, _parse_task
            my_task = asyncio.current_task()
            try:
                urls_list = read_urls(URLS_FILE)
            except OSError:
                urls_list = []
            n_urls = len(urls_list)
            resume = read_resume_index()
            if n_urls and resume >= n_urls:
                resume = 0
            _parse_progress.clear()
            _parse_progress.update(
                active=True,
                index=resume + 1 if n_urls else 0,
                total_urls=n_urls,
                current_skin=None,
            )
            try:
                await run_crawl(
                    stop_event=_stop_event,
                    continuous=True,
                    progress=_parse_progress,
                    resume_index=resume,
                )
            except asyncio.CancelledError:
                pass
            finally:
                _parse_progress["active"] = False
                if _parse_task is my_task:
                    _parse_task = None

        _parse_task = asyncio.create_task(runner())
    return {"ok": True}


@app.post("/api/pars/stop")
async def pars_stop():
    global _stop_event, _parse_task
    if _stop_event is not None:
        _stop_event.set()
    t = _parse_task
    if t is not None:
        if not t.done():
            t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        _parse_task = None
    return {"ok": True}


@app.get("/api/search/skins")
async def search_skins(q: str = ""):
    rows = await asyncio.to_thread(_sync_search_skins_rows)
    variants = query_variants(q)
    matches = []
    for name, item_count in rows:
        if not q.strip():
            matches.append({"skin_name": name, "item_count": item_count})
        elif skin_matches_filters(name, variants):
            matches.append({"skin_name": name, "item_count": item_count})
    return {"matches": matches}


class SkinsSearchBody(BaseModel):
    skins: list[str] = Field(default_factory=list)


class OptimizePrmBody(BaseModel):
    skins: list[str] = Field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    trophies_min: int | None = None
    trophies_max: int | None = None
    brawl_level_min: int | None = None
    brawl_level_max: int | None = None


class NotifyRuleBody(BaseModel):
    skins: list[str] = Field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    trophies_min: int | None = None
    trophies_max: int | None = None
    brawl_level_min: int | None = None
    brawl_level_max: int | None = None


class NotifySaveBody(BaseModel):
    telegram_bot_token: str = ""
    telegram_chat_ids: str = ""
    interval_sec: int = 60
    rules: list[NotifyRuleBody] = Field(default_factory=list)


class LoginBody(BaseModel):
    password: str = ""
    remember_me: bool = False


def _validate_opt_filters(
    *,
    price_min: float | None,
    price_max: float | None,
    trophies_min: int | None,
    trophies_max: int | None,
    brawl_level_min: int | None,
    brawl_level_max: int | None,
) -> None:
    if price_min is not None and price_max is not None and price_min > price_max:
        raise HTTPException(status_code=400, detail="price_min must be <= price_max")
    if trophies_min is not None and trophies_max is not None and trophies_min > trophies_max:
        raise HTTPException(
            status_code=400, detail="trophies_min must be <= trophies_max"
        )
    if brawl_level_min is not None and brawl_level_max is not None:
        if brawl_level_min > brawl_level_max:
            raise HTTPException(
                status_code=400, detail="brawl_level_min must be <= brawl_level_max"
            )


@app.post("/api/search/by-skins")
async def search_by_skins(body: SkinsSearchBody):
    raw = [s.strip() for s in body.skins if s and s.strip()]
    skins = list(dict.fromkeys(raw))
    if not skins:
        raise HTTPException(status_code=400, detail="no skins selected")
    return await asyncio.to_thread(_sync_search_by_skins_items, skins)


@app.get("/api/db/snapshot")
async def db_snapshot():
    global _db_snapshot_cache_payload, _db_snapshot_cache_mono
    now = time.monotonic()
    if (
        _db_snapshot_cache_payload is not None
        and now - _db_snapshot_cache_mono < _DB_SNAPSHOT_CACHE_SEC
    ):
        payload = _db_snapshot_cache_payload
    else:
        async with _db_snapshot_refresh_lock:
            now = time.monotonic()
            if (
                _db_snapshot_cache_payload is not None
                and now - _db_snapshot_cache_mono < _DB_SNAPSHOT_CACHE_SEC
            ):
                payload = _db_snapshot_cache_payload
            else:
                payload = await asyncio.to_thread(_sync_db_snapshot_payload)
                _db_snapshot_cache_payload = payload
                _db_snapshot_cache_mono = time.monotonic()
    return {
        "server_time": datetime.now(timezone.utc).isoformat(),
        **payload,
    }


@app.post("/api/db/clear-nonfatal-skin-errors")
async def db_clear_nonfatal_skin_errors():
    """Clear skins.error for transient browser/transport/timeout messages; keep other errors."""
    n = await asyncio.to_thread(_sync_clear_nonfatal_skin_errors)
    return {"cleared": n}


@app.get("/api/optimize/top")
async def optimize_top(limit: int = 80):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be 1-500")
    return await asyncio.to_thread(compute_top_deals, DB_PATH, limit=limit)


@app.post("/api/optimize/prm")
async def optimize_prm(body: OptimizePrmBody, limit: int = 120):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be 1-500")
    raw = [s.strip() for s in body.skins if s and s.strip()]
    skins = list(dict.fromkeys(raw))
    if not skins:
        raise HTTPException(status_code=400, detail="no skins selected")
    _validate_opt_filters(
        price_min=body.price_min,
        price_max=body.price_max,
        trophies_min=body.trophies_min,
        trophies_max=body.trophies_max,
        brawl_level_min=body.brawl_level_min,
        brawl_level_max=body.brawl_level_max,
    )

    def run_prm() -> dict:
        return compute_top_deals_for_required_skins(
            DB_PATH,
            skins,
            limit=limit,
            price_min=body.price_min,
            price_max=body.price_max,
            trophies_min=body.trophies_min,
            trophies_max=body.trophies_max,
            brawl_level_min=body.brawl_level_min,
            brawl_level_max=body.brawl_level_max,
        )

    return await asyncio.to_thread(run_prm)


@app.get("/api/notify/config")
async def notify_config_get():
    return load_config_for_api()


@app.post("/api/notify/config")
async def notify_config_post(body: NotifySaveBody):
    for r in body.rules:
        _validate_opt_filters(
            price_min=r.price_min,
            price_max=r.price_max,
            trophies_min=r.trophies_min,
            trophies_max=r.trophies_max,
            brawl_level_min=r.brawl_level_min,
            brawl_level_max=r.brawl_level_max,
        )
    try:
        saved = await save_config_from_body_locked(body.model_dump())
        return {"ok": True, "config": saved}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/sell/compose")
async def sell_compose(id: str):
    ident = id.strip()
    if not ident.isdigit():
        raise HTTPException(status_code=400, detail="id must be numeric")
    try:
        return await asyncio.to_thread(_sync_sell_compose, ident)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/api/search/by-item")
async def search_by_item(id: str):
    ident = id.strip()
    if not ident.isdigit():
        raise HTTPException(status_code=400, detail="id must be numeric")
    skins = await asyncio.to_thread(_sync_search_by_item_skins, ident)
    return {"skin_names": skins}


@app.get("/")
async def root_entry(request: Request):
    if not gate_enabled():
        return RedirectResponse(url="/parsing/", status_code=302)
    if not gate_request_ok(request):
        return not_found()
    return RedirectResponse(url="/login/", status_code=302)


@app.get("/login")
@app.get("/login/")
async def gate_login_get(request: Request):
    if not gate_enabled():
        return not_found()
    if not gate_request_ok(request):
        return not_found()
    if not GATE_LOGIN_HTML.is_file():
        raise HTTPException(status_code=503, detail="login page missing")
    return FileResponse(GATE_LOGIN_HTML, media_type="text/html")


@app.post("/api/auth/login")
async def gate_login_post(request: Request, body: LoginBody):
    if not gate_enabled():
        return not_found()
    if not gate_request_ok(request):
        return not_found()
    ip = client_ip(request)
    if await ip_login_is_rate_limited(ip):
        return not_found()
    if not verify_login_password(body.password):
        await ip_login_note_failure(ip)
        return not_found()
    await ip_login_note_success(ip)
    resp = JSONResponse({"ok": True})
    attach_refreshed_cookie(resp, request, body.remember_me)
    return resp


@app.post("/api/auth/logout")
async def gate_logout_post():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


SONIK_JPG = ROOT / "sonik.jpg"


_ICON_NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


@app.get("/sonik.jpg")
async def sonik_jpg():
    if not SONIK_JPG.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(
        SONIK_JPG, media_type="image/jpeg", headers=_ICON_NO_CACHE
    )


@app.get("/favicon.ico")
async def favicon_ico():
    """Browsers default to /favicon.ico; no separate .ico file — same image as sonik."""
    if not SONIK_JPG.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(
        SONIK_JPG, media_type="image/jpeg", headers=_ICON_NO_CACHE
    )


assets_dir = FRONTEND_DIST / "assets"
if assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/{full_path:path}")
async def spa_or_static(full_path: str):
    if full_path.startswith("api"):
        raise HTTPException(status_code=404)
    if full_path == "" or full_path.endswith("/"):
        idx = FRONTEND_DIST / "index.html"
        if idx.is_file():
            return FileResponse(idx)
        raise HTTPException(status_code=503, detail="frontend not built")
    file_path = FRONTEND_DIST / full_path
    if file_path.is_file():
        return FileResponse(file_path)
    idx = FRONTEND_DIST / "index.html"
    if idx.is_file():
        return FileResponse(idx)
    raise HTTPException(status_code=503, detail="frontend not built")


@app.middleware("http")
async def _sonic_gate_middleware(request: Request, call_next):
    return await gate_middleware(request, call_next)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=13337,
        reload=False,
    )


if __name__ == "__main__":
    main()
