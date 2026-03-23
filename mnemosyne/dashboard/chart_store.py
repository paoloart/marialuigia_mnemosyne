import json
import sqlite3
from datetime import datetime, timezone


def ensure_table(conn: sqlite3.Connection) -> None:
    """Create dashboard_charts table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_charts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            chart_type TEXT NOT NULL,
            data_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            pinned INTEGER DEFAULT 0
        )
    """)
    conn.commit()


def insert_chart(conn: sqlite3.Connection, title: str, chart_type: str,
                 data, pinned: bool = False) -> int:
    """Insert a chart record. data can be a dict/list (JSON-serialised) or a string."""
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)
    cur = conn.execute(
        "INSERT INTO dashboard_charts (title, chart_type, data_json, created_at, pinned) "
        "VALUES (?, ?, ?, ?, ?)",
        (title, chart_type, data, datetime.now(timezone.utc).isoformat(), int(pinned)),
    )
    conn.commit()
    return cur.lastrowid


def get_charts(conn: sqlite3.Connection, limit: int = 50,
               since_id: int | None = None) -> list[dict]:
    """Return charts ordered by pinned DESC, created_at DESC."""
    if since_id is not None:
        rows = conn.execute(
            "SELECT * FROM dashboard_charts WHERE id > ? "
            "ORDER BY pinned DESC, created_at DESC LIMIT ?",
            (since_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM dashboard_charts "
            "ORDER BY pinned DESC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_id(conn: sqlite3.Connection) -> int:
    """Return the highest chart id, or 0 if table is empty."""
    row = conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM dashboard_charts"
    ).fetchone()
    return row[0]


def delete_unpinned(conn: sqlite3.Connection) -> int:
    """Delete all non-pinned charts. Returns number of rows deleted."""
    cur = conn.execute("DELETE FROM dashboard_charts WHERE pinned = 0")
    conn.commit()
    return cur.rowcount
