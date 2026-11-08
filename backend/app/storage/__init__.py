"""SQLite storage at data/safesignal.db (Track B).

Holds only hashed numbers, states and counts: no raw numbers, transcripts or audio.
Reset never touches this data.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "safesignal.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS consent (
    phone_hash TEXT PRIMARY KEY,
    state TEXT NOT NULL CHECK (state IN ('invited', 'active', 'stopped')),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reply_counts (
    keyword TEXT NOT NULL,
    template_id TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (keyword, template_id)
);
CREATE TABLE IF NOT EXISTS aggregates (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS policy_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def init() -> None:
    """Create tables (idempotent). Called by main.py at startup."""
    with closing(connect()):
        pass


def incr_reply(keyword: str, template_id: str) -> int:
    """Count one reply; return the new running total for that keyword across templates."""
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO reply_counts (keyword, template_id, count) VALUES (?, ?, 1) "
            "ON CONFLICT (keyword, template_id) DO UPDATE SET count = count + 1",
            (keyword, template_id),
        )
        return conn.execute("SELECT SUM(count) FROM reply_counts WHERE keyword = ?", (keyword,)).fetchone()[0]


def incr(name: str) -> int:
    """Increment a named aggregate counter; return its new value."""
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO aggregates (name, value) VALUES (?, 1) "
            "ON CONFLICT (name) DO UPDATE SET value = value + 1",
            (name,),
        )
        return conn.execute("SELECT value FROM aggregates WHERE name = ?", (name,)).fetchone()[0]


def record_policy(version: str, note: str = "") -> None:
    with closing(connect()) as conn, conn:
        conn.execute("INSERT INTO policy_history (version, note) VALUES (?, ?)", (version, note))


def aggregates() -> dict:
    """Everything GET /aggregates serves: counters, reply counts and policy history."""
    with closing(connect()) as conn:
        counters = dict(conn.execute("SELECT name, value FROM aggregates ORDER BY name"))
        replies = [
            {"keyword": k, "template_id": t, "count": c}
            for k, t, c in conn.execute(
                "SELECT keyword, template_id, count FROM reply_counts ORDER BY keyword, template_id")
        ]
        policy = [
            {"version": v, "note": n, "at": a}
            for v, n, a in conn.execute("SELECT version, note, at FROM policy_history ORDER BY id")
        ]
    return {"counters": counters, "replies": replies, "policy_history": policy}
