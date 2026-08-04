from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from market_listing import ItemListingRow

# In-flight browser restart (transport / pipe only).
SKIN_TRANSPORT_ERR_MARKERS: tuple[str, ...] = (
    "WriteUnixTransport",
    "Target page, context or browser has been closed",
    "Browser has been closed",
    "Connection closed",
    "EPIPE",
    "Broken pipe",
    "WebSocket error",
)

# Transient crawl failures safe to clear from skins.error (transport + timeouts / driver).
SKIN_NONFATAL_ERR_MARKERS: tuple[str, ...] = SKIN_TRANSPORT_ERR_MARKERS + (
    "reading from the driver",
    "Target crashed",
    "TimeoutError",
    "ms exceeded",
    "net::ERR_TIMED_OUT",
    "net::ERR_CONNECTION_RESET",
    "net::ERR_ABORTED",
    "NS_BINDING_ABORTED",
)


def is_nonfatal_skin_error(message: str | None) -> bool:
    if not message or not message.strip():
        return False
    return any(m in message for m in SKIN_NONFATAL_ERR_MARKERS)


def clear_nonfatal_skin_errors(conn: sqlite3.Connection) -> int:
    """Set error to NULL for rows whose error text looks transient (browser/transport/timeout)."""
    rows = conn.execute(
        "SELECT skin_name, error FROM skins WHERE error IS NOT NULL AND trim(error) != ''"
    ).fetchall()
    cleared = 0
    for skin_name, err in rows:
        if is_nonfatal_skin_error(err):
            conn.execute(
                "UPDATE skins SET error = NULL WHERE skin_name = ?",
                (skin_name,),
            )
            cleared += 1
    return cleared


def init_sqlite(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS skins (
            skin_name TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            item_count INTEGER NOT NULL DEFAULT 0,
            fetched_at TEXT NOT NULL,
            error TEXT
        );
        CREATE TABLE IF NOT EXISTS skin_items (
            skin_name TEXT NOT NULL,
            item_id TEXT NOT NULL,
            PRIMARY KEY (skin_name, item_id),
            FOREIGN KEY (skin_name) REFERENCES skins(skin_name)
        );
        CREATE INDEX IF NOT EXISTS idx_skin_items_skin ON skin_items(skin_name);
        CREATE INDEX IF NOT EXISTS idx_skin_items_item ON skin_items(item_id);
        CREATE TABLE IF NOT EXISTS item_brawl_stats (
            item_id TEXT PRIMARY KEY,
            brawl_level INTEGER,
            trophies INTEGER,
            brawlers INTEGER,
            legendary INTEGER,
            hypercharges INTEGER,
            price REAL,
            currency TEXT,
            updated_at TEXT NOT NULL
        );
        """
    )


def upsert_item_brawl_stats(
    conn: sqlite3.Connection, rows: dict[str, ItemListingRow]
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    sql = """
        INSERT INTO item_brawl_stats (
            item_id, brawl_level, trophies, brawlers, legendary, hypercharges,
            price, currency, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(item_id) DO UPDATE SET
            brawl_level = COALESCE(excluded.brawl_level, item_brawl_stats.brawl_level),
            trophies = COALESCE(excluded.trophies, item_brawl_stats.trophies),
            brawlers = COALESCE(excluded.brawlers, item_brawl_stats.brawlers),
            legendary = COALESCE(excluded.legendary, item_brawl_stats.legendary),
            hypercharges = COALESCE(excluded.hypercharges, item_brawl_stats.hypercharges),
            price = COALESCE(excluded.price, item_brawl_stats.price),
            currency = COALESCE(excluded.currency, item_brawl_stats.currency),
            updated_at = excluded.updated_at
    """
    for r in rows.values():
        conn.execute(
            sql,
            (
                r.item_id,
                r.brawl_level,
                r.trophies,
                r.brawlers,
                r.legendary,
                r.hypercharges,
                r.price,
                r.currency,
                now,
            ),
        )


def upsert_skin_rows(
    conn: sqlite3.Connection,
    skin_name: str,
    url: str,
    ids: list[str] | None,
    err: str | None,
    listing_rows: dict[str, ItemListingRow] | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    cnt = len(ids) if ids else 0
    conn.execute(
        """
        INSERT INTO skins(skin_name, url, item_count, fetched_at, error)
        VALUES (?,?,?,?,?)
        ON CONFLICT(skin_name) DO UPDATE SET
            url=excluded.url,
            item_count=excluded.item_count,
            fetched_at=excluded.fetched_at,
            error=excluded.error
        """,
        (skin_name, url, cnt, now, err),
    )
    conn.execute("DELETE FROM skin_items WHERE skin_name = ?", (skin_name,))
    if ids:
        conn.executemany(
            "INSERT INTO skin_items(skin_name, item_id) VALUES (?,?)",
            [(skin_name, iid) for iid in ids],
        )
    if ids and listing_rows:
        subset = {iid: listing_rows[iid] for iid in ids if iid in listing_rows}
        if subset:
            upsert_item_brawl_stats(conn, subset)


def configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    configure_connection(conn)
    init_sqlite(conn)
    conn.commit()
    return conn
