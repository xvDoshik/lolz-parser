from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from crawl_worker import DB_PATH
from optimize_rank import compute_top_deals_for_required_skins
from sell_listing import build_sell_bundle

ROOT = Path(__file__).resolve().parent
NOTIFY_CONFIG_PATH = ROOT / ".notify_config.json"

_log = logging.getLogger("sonicparser.notify")
_notify_lock = asyncio.Lock()


def _read_file() -> dict[str, Any] | None:
    try:
        raw = NOTIFY_CONFIG_PATH.read_text(encoding="utf-8")
        return json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None


def _write_file(data: dict[str, Any]) -> None:
    NOTIFY_CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _parse_chat_ids(s: str) -> list[int]:
    out: list[int] = []
    for part in re.split(r"[,\s;]+", (s or "").strip()):
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def _fmt_price_usd(price: float, currency: str | None) -> str:
    cur = (currency or "").strip().upper()
    if cur in ("", "USD", "US$"):
        return f"${float(price):.2f}"
    return f"{float(price):.2f} {cur}".strip()


def _build_telegram_text(
    item_id: str,
    price: float,
    currency: str | None,
    title: str,
    description: str,
) -> str:
    url = f"https://lzt.market/{item_id}/"
    price_s = _fmt_price_usd(price, currency)
    lines = [
        "Обнаружен новый выгодный аккаунт",
        "",
        f"{url}  ({price_s})",
        "",
        title,
        "",
        description,
    ]
    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3790] + "\n…(обрезано)"
    return text


def _fetch_stats_skins(conn: sqlite3.Connection, item_id: str) -> tuple[dict | None, list[str]]:
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT item_id, brawl_level, trophies, brawlers, legendary,
               hypercharges, price, currency
        FROM item_brawl_stats
        WHERE item_id = ?
        """,
        (item_id,),
    ).fetchone()
    stats = dict(row) if row else None
    cur = conn.execute(
        """
        SELECT DISTINCT skin_name FROM skin_items
        WHERE item_id = ?
        ORDER BY skin_name COLLATE NOCASE
        """,
        (item_id,),
    )
    skins = [r[0] for r in cur.fetchall()]
    return stats, skins


def _send_telegram_sync(token: str, chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": False},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        body = resp.read()
    data = json.loads(body.decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(str(data.get("description") or data))


async def send_telegram_to_all(token: str, chat_ids: list[int], text: str) -> None:
    for cid in chat_ids:
        await asyncio.to_thread(_send_telegram_sync, token, cid, text)


def normalize_rules_from_post(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rules:
        raw_skins = r.get("skins") or []
        skins = sorted(
            dict.fromkeys(str(s).strip() for s in raw_skins if str(s).strip())
        )
        if not skins:
            continue
        out.append(
            {
                "skins": skins,
                "price_min": r.get("price_min"),
                "price_max": r.get("price_max"),
                "trophies_min": r.get("trophies_min"),
                "trophies_max": r.get("trophies_max"),
                "brawl_level_min": r.get("brawl_level_min"),
                "brawl_level_max": r.get("brawl_level_max"),
                "baseline_score": None,
                "baseline_item_id": None,
            }
        )
    return out


def set_baselines_from_db(rules: list[dict[str, Any]]) -> None:
    for rule in rules:
        res = compute_top_deals_for_required_skins(
            DB_PATH,
            rule["skins"],
            limit=1,
            price_min=rule.get("price_min"),
            price_max=rule.get("price_max"),
            trophies_min=rule.get("trophies_min"),
            trophies_max=rule.get("trophies_max"),
            brawl_level_min=rule.get("brawl_level_min"),
            brawl_level_max=rule.get("brawl_level_max"),
        )
        items = res.get("items") or []
        if items:
            top = items[0]
            rule["baseline_score"] = float(top["score"])
            rule["baseline_item_id"] = str(top["item_id"])
        else:
            rule["baseline_score"] = None
            rule["baseline_item_id"] = None


def load_config_for_api() -> dict[str, Any]:
    data = _read_file()
    if not data:
        return {
            "telegram_bot_token": "",
            "telegram_chat_ids": "",
            "interval_sec": 60,
            "rules": [],
        }
    rules = data.get("rules") or []
    safe_rules = []
    for r in rules:
        safe_rules.append(
            {
                "skins": list(r.get("skins") or []),
                "price_min": r.get("price_min"),
                "price_max": r.get("price_max"),
                "trophies_min": r.get("trophies_min"),
                "trophies_max": r.get("trophies_max"),
                "brawl_level_min": r.get("brawl_level_min"),
                "brawl_level_max": r.get("brawl_level_max"),
                "baseline_score": r.get("baseline_score"),
                "baseline_item_id": r.get("baseline_item_id"),
            }
        )
    return {
        "telegram_bot_token": data.get("telegram_bot_token") or "",
        "telegram_chat_ids": data.get("telegram_chat_ids") or "",
        "interval_sec": int(data.get("interval_sec") or 60),
        "rules": safe_rules,
    }


def save_config_from_body(body: dict[str, Any]) -> dict[str, Any]:
    interval = int(body.get("interval_sec") or 60)
    interval = max(5, min(3000, interval))
    token = (body.get("telegram_bot_token") or "").strip()
    chat_ids_str = (body.get("telegram_chat_ids") or "").strip()
    rules = normalize_rules_from_post(body.get("rules") or [])
    if not rules:
        raise ValueError("нужен хотя бы один фильтр с выбранными скинами")
    if not token:
        raise ValueError("нужен токен бота Telegram")
    ids = _parse_chat_ids(chat_ids_str)
    if not ids:
        raise ValueError("нужен хотя бы один chat id (через запятую)")
    set_baselines_from_db(rules)
    data = {
        "telegram_bot_token": token,
        "telegram_chat_ids": chat_ids_str,
        "interval_sec": interval,
        "rules": rules,
    }
    _write_file(data)
    return load_config_for_api()


async def save_config_from_body_locked(body: dict[str, Any]) -> dict[str, Any]:
    async with _notify_lock:
        return save_config_from_body(body)


async def notify_tick_once() -> None:
    async with _notify_lock:
        raw = _read_file()
        if not raw:
            return
        n_rules = len(raw.get("rules") or [])
        token0 = (raw.get("telegram_bot_token") or "").strip()
        chat0 = _parse_chat_ids(str(raw.get("telegram_chat_ids") or ""))
        if not token0 or not chat0 or n_rules == 0:
            return

    conn = sqlite3.connect(DB_PATH)
    try:
        for i in range(n_rules):
            async with _notify_lock:
                cfg = _read_file()
                if not cfg:
                    break
                token = (cfg.get("telegram_bot_token") or "").strip()
                chat_ids = _parse_chat_ids(str(cfg.get("telegram_chat_ids") or ""))
                rules = list(cfg.get("rules") or [])
                if i >= len(rules) or not token or not chat_ids:
                    break
                rule = rules[i]
            skins = rule.get("skins") or []
            if not skins:
                continue
            res = compute_top_deals_for_required_skins(
                DB_PATH,
                skins,
                limit=1,
                price_min=rule.get("price_min"),
                price_max=rule.get("price_max"),
                trophies_min=rule.get("trophies_min"),
                trophies_max=rule.get("trophies_max"),
                brawl_level_min=rule.get("brawl_level_min"),
                brawl_level_max=rule.get("brawl_level_max"),
            )
            items = res.get("items") or []
            if not items:
                continue
            top = items[0]
            new_score = float(top["score"])
            new_id = str(top["item_id"])
            bs = rule.get("baseline_score")
            if bs is None:
                async with _notify_lock:
                    cfg = _read_file()
                    if not cfg:
                        continue
                    _patch_rule_baseline(cfg, rule, new_score, new_id)
                    _write_file(cfg)
                continue
            old = float(bs)
            if new_score <= old + 1e-12:
                continue

            prev_id = str(rule.get("baseline_item_id") or "")
            if prev_id and new_id == prev_id:
                async with _notify_lock:
                    cfg = _read_file()
                    if not cfg:
                        continue
                    _patch_rule_baseline(cfg, rule, new_score, new_id)
                    _write_file(cfg)
                continue

            stats, skin_list = _fetch_stats_skins(conn, new_id)
            bundle = build_sell_bundle(new_id, stats, skin_list)
            title = bundle.get("title") or "—"
            description = bundle.get("description") or "—"
            price = float(top.get("price") or 0)
            currency = top.get("currency")
            text = _build_telegram_text(new_id, price, currency, title, description)
            try:
                await send_telegram_to_all(token, chat_ids, text)
            except (urllib.error.HTTPError, urllib.error.URLError, OSError, RuntimeError) as ex:
                _log.warning("telegram send failed: %s", ex)
                continue

            async with _notify_lock:
                cfg = _read_file()
                if not cfg:
                    continue
                _patch_rule_baseline(cfg, rule, new_score, new_id)
                _write_file(cfg)
    finally:
        conn.close()


def _patch_rule_baseline(
    cfg: dict[str, Any],
    rule_template: dict[str, Any],
    new_score: float,
    new_id: str,
) -> None:
    key = _rule_key(rule_template)
    for r in cfg.get("rules") or []:
        if _rule_key(r) == key:
            r["baseline_score"] = new_score
            r["baseline_item_id"] = new_id
            return


def _rule_key(r: dict[str, Any]) -> tuple:
    sk = r.get("skins") or ()
    return (
        tuple(sorted(sk)),
        r.get("price_min"),
        r.get("price_max"),
        r.get("trophies_min"),
        r.get("trophies_max"),
        r.get("brawl_level_min"),
        r.get("brawl_level_max"),
    )


async def notification_background_loop(stop: asyncio.Event) -> None:
    _log.info("notification background loop started")
    try:
        while not stop.is_set():
            interval = 60.0
            try:
                raw = _read_file()
                if raw:
                    interval = float(
                        max(5, min(3000, int(raw.get("interval_sec") or 60))))
                    token = (raw.get("telegram_bot_token") or "").strip()
                    ids = _parse_chat_ids(str(raw.get("telegram_chat_ids") or ""))
                    if token and ids and (raw.get("rules") or []):
                        await notify_tick_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("notify tick error")
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass
    finally:
        _log.info("notification background loop stopped")
