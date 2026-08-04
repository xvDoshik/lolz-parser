from __future__ import annotations

import math
import sqlite3
from pathlib import Path


def _i(v: object) -> int:
    if v is None:
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _value_numerator(row: dict) -> float:
    t = _i(row.get("trophies"))
    b = _i(row.get("brawlers"))
    leg = _i(row.get("legendary"))
    hyp = _i(row.get("hypercharges"))
    lvl = _i(row.get("brawl_level"))
    return (
        min(t, 80000) * 0.001
        + min(b, 100) * 3.0
        + leg * 18.0
        + hyp * 10.0
        + min(lvl, 300) * 0.25
    )


def _lvl_weight_v2(lvl: int) -> float:
    """
    Штраф за низкий brawl_level: дешёвый аккаунт 13 lvl не должен бить топ
    только за value/price — «с такого мало заработаешь».
    w = clip((min(lvl, 80) / 40)^1.15, 0.25, 1.0)
    """
    if lvl <= 0:
        return 0.25
    x = min(float(lvl), 80.0) / 40.0
    w = math.pow(x, 1.15)
    return max(0.25, min(1.0, w))


_FORMULA_V1 = (
    "value_score = (LEAST(trophies,80000)*0.001 + LEAST(brawlers,100)*3 "
    "+ legendary*18 + hypercharges*10 + LEAST(brawl_level,300)*0.25) / price"
)


def _rows_to_scored(rows: list[dict]) -> list[dict]:
    scored: list[dict] = []
    for r in rows:
        price = float(r["price"])
        if price <= 0:
            continue
        iid = str(r["item_id"])
        numer = _value_numerator(r)
        score = numer / price
        scored.append(
            {
                "item_id": iid,
                "url": f"https://lzt.market/{iid}/",
                "price": r["price"],
                "currency": r["currency"],
                "brawl_level": r["brawl_level"],
                "trophies": r["trophies"],
                "brawlers": r["brawlers"],
                "legendary": r["legendary"],
                "hypercharges": r["hypercharges"],
                "skin_tags": int(r["skin_tags"] or 0),
                "value_numerator": round(numer, 4),
                "score": round(score, 8),
            }
        )
    return scored


def _finalize_with_lvl_weight(
    scored: list[dict],
    meta_base: dict,
    *,
    limit: int,
) -> dict:
    items: list[dict] = []
    for it in scored:
        lvl = _i(it.get("brawl_level"))
        w = _lvl_weight_v2(lvl)
        raw = float(it["score"])
        adj = raw * w
        row = dict(it)
        row["score_v1"] = it["score"]
        row["lvl_weight"] = round(w, 6)
        row["score"] = round(adj, 8)
        items.append(row)
    items.sort(key=lambda x: -x["score"])
    top = items[: max(1, min(limit, 500))]
    meta = dict(meta_base)
    meta["returned"] = len(top)
    return {"items": top, "meta": meta}


def _build_all_scored(db_path: Path) -> tuple[list[dict], dict]:
    """Полный список с value_score (v1); без slice."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT s.item_id, s.price, s.currency,
                   s.brawl_level, s.trophies, s.brawlers, s.legendary, s.hypercharges,
                   (SELECT COUNT(*) FROM skin_items si WHERE si.item_id = s.item_id) AS skin_tags
            FROM item_brawl_stats s
            WHERE s.price IS NOT NULL AND s.price > 0
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    scored = _rows_to_scored(rows)
    meta_base = {
        "total_rows": len(rows),
        "total_scored": len(scored),
        "formula": _FORMULA_V1,
    }
    return scored, meta_base


def _build_scored_for_required_skins(
    db_path: Path,
    required_skins: list[str],
    *,
    price_min: float | None = None,
    price_max: float | None = None,
    trophies_min: int | None = None,
    trophies_max: int | None = None,
    brawl_level_min: int | None = None,
    brawl_level_max: int | None = None,
) -> tuple[list[dict], dict]:
    """
    Только лоты, у которых в skin_items есть все перечисленные скины
    (COUNT(DISTINCT skin_name) = N по фильтру IN), плюс опциональные пороги по цене/кубкам/lvl.
    """
    skins = list(
        dict.fromkeys(s.strip() for s in required_skins if s and str(s).strip())
    )
    if not skins:
        return [], {
            "total_rows": 0,
            "total_scored": 0,
            "required_skins": [],
            "required_count": 0,
            "formula": _FORMULA_V1,
        }

    n = len(skins)
    ph = ",".join("?" * n)
    extra_sql: list[str] = []
    extra_params: list[object] = []
    if price_min is not None:
        extra_sql.append("AND s.price >= ?")
        extra_params.append(float(price_min))
    if price_max is not None:
        extra_sql.append("AND s.price <= ?")
        extra_params.append(float(price_max))
    if trophies_min is not None:
        extra_sql.append(
            "AND s.trophies IS NOT NULL AND CAST(s.trophies AS INTEGER) >= ?"
        )
        extra_params.append(int(trophies_min))
    if trophies_max is not None:
        extra_sql.append(
            "AND s.trophies IS NOT NULL AND CAST(s.trophies AS INTEGER) <= ?"
        )
        extra_params.append(int(trophies_max))
    if brawl_level_min is not None:
        extra_sql.append(
            "AND s.brawl_level IS NOT NULL AND CAST(s.brawl_level AS INTEGER) >= ?"
        )
        extra_params.append(int(brawl_level_min))
    if brawl_level_max is not None:
        extra_sql.append(
            "AND s.brawl_level IS NOT NULL AND CAST(s.brawl_level AS INTEGER) <= ?"
        )
        extra_params.append(int(brawl_level_max))

    where_extra = (" " + " ".join(extra_sql)) if extra_sql else ""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            f"""
            SELECT s.item_id, s.price, s.currency,
                   s.brawl_level, s.trophies, s.brawlers, s.legendary, s.hypercharges,
                   (SELECT COUNT(*) FROM skin_items si WHERE si.item_id = s.item_id) AS skin_tags
            FROM item_brawl_stats s
            INNER JOIN (
                SELECT item_id
                FROM skin_items
                WHERE skin_name IN ({ph})
                GROUP BY item_id
                HAVING COUNT(DISTINCT skin_name) = ?
            ) req ON req.item_id = s.item_id
            WHERE s.price IS NOT NULL AND s.price > 0{where_extra}
            """,
            (*skins, n, *extra_params),
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    scored = _rows_to_scored(rows)
    meta_base = {
        "total_rows": len(rows),
        "total_scored": len(scored),
        "required_skins": skins,
        "required_count": n,
        "filters": {
            "price_min": price_min,
            "price_max": price_max,
            "trophies_min": trophies_min,
            "trophies_max": trophies_max,
            "brawl_level_min": brawl_level_min,
            "brawl_level_max": brawl_level_max,
        },
        "formula": _FORMULA_V1,
    }
    return scored, meta_base


def compute_top_deals(db_path: Path, *, limit: int = 80) -> dict:
    """
    value/price как базовый score, затем score *= w(brawl_level) —
    низкий lvl не забирает топ только из‑за дешевизны.
    """
    scored, meta_base = _build_all_scored(db_path)
    return _finalize_with_lvl_weight(scored, meta_base, limit=limit)


def compute_top_deals_for_required_skins(
    db_path: Path,
    required_skins: list[str],
    *,
    limit: int = 80,
    price_min: float | None = None,
    price_max: float | None = None,
    trophies_min: int | None = None,
    trophies_max: int | None = None,
    brawl_level_min: int | None = None,
    brawl_level_max: int | None = None,
) -> dict:
    """Как Opt, но только аккаунты, на которых точно есть все выбранные скины."""
    scored, meta_base = _build_scored_for_required_skins(
        db_path,
        required_skins,
        price_min=price_min,
        price_max=price_max,
        trophies_min=trophies_min,
        trophies_max=trophies_max,
        brawl_level_min=brawl_level_min,
        brawl_level_max=brawl_level_max,
    )
    return _finalize_with_lvl_weight(scored, meta_base, limit=limit)
