from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator


@dataclass
class ItemListingRow:
    item_id: str
    brawl_level: int | None = None
    trophies: int | None = None
    brawlers: int | None = None
    legendary: int | None = None
    hypercharges: int | None = None
    price: float | None = None
    currency: str | None = None


_ITEM_OPEN = re.compile(r'<div id="marketItem--(\d+)"')


def _ru_int_fragment(s: str) -> int | None:
    s = re.sub(r"[\s\u00a0]", "", s)
    if not s.isdigit():
        return None
    return int(s)


def _first_float_data_value(block: str) -> float | None:
    m = re.search(r'class="Value"[^>]*data-value="([\d.]+)"', block)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _currency_from_block(block: str) -> str | None:
    if "svgIcon--usd" in block:
        return "USD"
    if "svgIcon--eur" in block:
        return "EUR"
    if "svgIcon--rub" in block:
        return "RUB"
    return None


def _brawl_badge_segment(block: str) -> str | None:
    key = "badgeIc-BrawlStars"
    i = block.find(key)
    if i < 0:
        return None
    sub = block[i:]
    m = re.search(r"badgeIc-(?:clash-royale|clash-of-clans)\b", sub[40:])
    if m:
        sub = sub[: m.start() + 40]
    return sub


def _simple_badge_texts(seg: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(
        r'<div class="marketIndexItem-Badge">\s*(.*?)\s*</div>', seg, re.DOTALL
    ):
        inner = m.group(1)
        inner = re.sub(r"<[^>]+>", "", inner)
        t = " ".join(inner.split())
        if t:
            out.append(t)
    return out


def _parse_badge_texts(texts: list[str]) -> tuple[
    int | None, int | None, int | None, int | None, int | None
]:
    level = trophies = brawlers = legendary = hyper = None
    low = [x.lower() for x in texts]
    for raw, lo in zip(texts, low):
        if "гиперзаряд" in lo:
            m = re.match(r"([\d\s\u00a0]+)", raw)
            if m:
                hyper = _ru_int_fragment(m.group(1))
            continue
        if "легендарн" in lo:
            m = re.match(r"([\d\s\u00a0]+)", raw)
            if m:
                legendary = _ru_int_fragment(m.group(1))
            continue
        if "кубков" in lo:
            m = re.match(r"([\d\s\u00a0]+)", raw)
            if m:
                trophies = _ru_int_fragment(m.group(1))
            continue
        if re.search(r"боец|бойца|бойцов", lo) and "легендарн" not in lo:
            m = re.match(r"([\d\s\u00a0]+)", raw)
            if m:
                brawlers = _ru_int_fragment(m.group(1))
            continue
        if "уровень" in lo and "корол" not in lo:
            m = re.match(r"([\d\s\u00a0]+)", raw)
            if m:
                level = _ru_int_fragment(m.group(1))
            continue
    return level, trophies, brawlers, legendary, hyper


def _parse_one_block(block: str) -> ItemListingRow | None:
    m = _ITEM_OPEN.search(block)
    if not m:
        return None
    iid = m.group(1)
    price = _first_float_data_value(block)
    currency = _currency_from_block(block)
    seg = _brawl_badge_segment(block)
    if seg is None:
        return ItemListingRow(
            item_id=iid,
            price=price,
            currency=currency,
        )
    texts = _simple_badge_texts(seg)
    level, trophies, brawlers, legendary, hyper = _parse_badge_texts(texts)
    return ItemListingRow(
        item_id=iid,
        brawl_level=level,
        trophies=trophies,
        brawlers=brawlers,
        legendary=legendary,
        hypercharges=hyper,
        price=price,
        currency=currency,
    )


def iter_market_item_blocks(html: str) -> Iterator[tuple[str, str]]:
    matches = list(_ITEM_OPEN.finditer(html))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        yield m.group(1), html[start:end]


def parse_listing_rows(html: str) -> tuple[list[str], dict[str, ItemListingRow]]:
    rows: dict[str, ItemListingRow] = {}
    order: list[str] = []
    for iid, block in iter_market_item_blocks(html):
        row = _parse_one_block(block)
        if row is None:
            continue
        if iid not in rows:
            order.append(iid)
        rows[iid] = row
    return order, rows


def parse_item_ids(html: str) -> list[str]:
    order, _ = parse_listing_rows(html)
    return order
