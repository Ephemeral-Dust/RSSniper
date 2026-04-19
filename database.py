import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

DB_FILE = Path("seen_items.db")


def init_db(db_path: Path = DB_FILE) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_items (
            id        TEXT PRIMARY KEY,
            feed      TEXT NOT NULL,
            title     TEXT,
            url       TEXT,
            published TEXT DEFAULT '',
            seen_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Migration: add published column to existing seen_items tables.
    # Track whether this is the first time the column is being added so we can
    # force a full lookback re-fetch to backfill published dates.
    _published_col_added = False
    try:
        conn.execute(
            "ALTER TABLE seen_items ADD COLUMN published TEXT DEFAULT ''"
        )
        _published_col_added = True
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feed_checks (
            feed_name       TEXT PRIMARY KEY,
            last_checked_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_matches (
            item_id      TEXT NOT NULL,
            monitor_name TEXT NOT NULL,
            matched_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            price        REAL,
            published    TEXT DEFAULT '',
            PRIMARY KEY (item_id, monitor_name)
        )
        """
    )
    # Migration: add columns to existing databases that predate them
    for _col_sql in [
        "ALTER TABLE deal_matches ADD COLUMN price REAL",
        "ALTER TABLE deal_matches ADD COLUMN published TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(_col_sql)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    # If the published column was just added, clear last_checked timestamps so
    # the next feed check re-fetches the full lookback window and can backfill
    # published dates for all recently-seen items.
    if _published_col_added:
        conn.execute("DELETE FROM feed_checks")
        conn.commit()
    return conn


def is_seen(conn: sqlite3.Connection, item_id: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM seen_items WHERE id = ?", (item_id,)
        ).fetchone()
        is not None
    )


def mark_seen(
    conn: sqlite3.Connection,
    item_id: str,
    feed: str,
    title: str,
    url: str,
    published: str = "",
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO seen_items (id, feed, title, url, published) VALUES (?, ?, ?, ?, ?)",
        (item_id, feed, title, url, published),
    )
    # Backfill published for rows that existed before the column was added
    if published:
        conn.execute(
            "UPDATE seen_items SET published = ? WHERE id = ? AND (published IS NULL OR published = '')",
            (published, item_id),
        )
    conn.commit()


def get_last_checked(
    conn: sqlite3.Connection, feed_name: str
) -> Optional[datetime]:
    """Return the last time this feed was fully checked as a UTC-aware datetime, or None."""
    row = conn.execute(
        "SELECT last_checked_at FROM feed_checks WHERE feed_name = ?",
        (feed_name,),
    ).fetchone()
    if row is None:
        return None
    try:
        dt = datetime.fromisoformat(row[0])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def set_last_checked(conn: sqlite3.Connection, feed_name: str) -> None:
    """Record that this feed was just fully checked (stores UTC time)."""
    conn.execute(
        "INSERT OR REPLACE INTO feed_checks (feed_name, last_checked_at) VALUES (?, ?)",
        (feed_name, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def is_deal_matched(
    conn: sqlite3.Connection, item_id: str, monitor_name: str
) -> bool:
    """Return True if this (item, monitor) pair has already been reported."""
    return (
        conn.execute(
            "SELECT 1 FROM deal_matches WHERE item_id = ? AND monitor_name = ?",
            (item_id, monitor_name),
        ).fetchone()
        is not None
    )


def mark_deal_matched(
    conn: sqlite3.Connection,
    item_id: str,
    monitor_name: str,
    price: Optional[float] = None,
    published: str = "",
) -> None:
    """Record that this (item, monitor) pair has been reported as a deal."""
    conn.execute(
        """
        INSERT OR IGNORE INTO deal_matches (item_id, monitor_name, price, published)
        VALUES (?, ?, ?, ?)
        """,
        (item_id, monitor_name, price, published),
    )
    conn.commit()


def sync_deal_matches_published(conn: sqlite3.Connection) -> None:
    """Copy published dates from seen_items into deal_matches where missing.

    Called after each feed check so that deal_matches.published stays in sync
    with seen_items.published as the backfill propagates.
    """
    conn.execute(
        """
        UPDATE deal_matches
        SET published = (
            SELECT si.published
            FROM seen_items si
            WHERE si.id = deal_matches.item_id
              AND si.published IS NOT NULL
              AND si.published != ''
        )
        WHERE (published IS NULL OR published = '')
          AND EXISTS (
              SELECT 1 FROM seen_items si
              WHERE si.id = deal_matches.item_id
                AND si.published IS NOT NULL
                AND si.published != ''
          )
        """
    )
    conn.commit()


def get_recent_deal_matches(
    conn: sqlite3.Connection, since: datetime
) -> list[dict]:
    """Return all deal_matches joined with seen_items for the Deals tab UI.

    Ordered newest-matched first.  *since* must be UTC-aware.
    Falls back to seen_items.published when deal_matches.published is empty.
    """
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        """
        SELECT
            dm.item_id,
            dm.monitor_name,
            dm.matched_at,
            dm.price,
            COALESCE(NULLIF(dm.published, ''), si.published, '') AS published,
            si.feed,
            si.title,
            si.url
        FROM deal_matches dm
        JOIN seen_items si ON si.id = dm.item_id
        WHERE dm.matched_at >= ?
        ORDER BY dm.matched_at DESC
        """,
        (since_str,),
    ).fetchall()
    return [
        {
            "item_id": r[0],
            "monitor_name": r[1],
            "matched_at": r[2],
            "price": r[3],
            "published": r[4] or "",
            "feed": r[5] or "",
            "title": r[6] or "",
            "url": r[7] or "",
        }
        for r in rows
    ]


def get_seen_items_since(
    conn: sqlite3.Connection, since: datetime
) -> list[dict]:
    """Return seen_items rows with seen_at >= *since* (since must be UTC-aware)."""
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        "SELECT id, feed, title, url, published FROM seen_items WHERE seen_at >= ?",
        (since_str,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "feed": r[1],
            "title": r[2] or "",
            "url": r[3] or "",
            "published": r[4] or "",
        }
        for r in rows
    ]
