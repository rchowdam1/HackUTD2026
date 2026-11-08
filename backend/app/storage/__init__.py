"""SQLite storage at data/safesignal.db (Track B).

Holds only hashed numbers, states and counts: no raw numbers, transcripts or audio.
Reset never touches this data.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing

from app import ROOT

DB_PATH = ROOT / "data" / "safesignal.db"

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
CREATE TABLE IF NOT EXISTS inbound_seen (
    message_id TEXT PRIMARY KEY,
    at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS operator_sessions (
    id_hash TEXT PRIMARY KEY,
    expires_at REAL NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    return conn


def init() -> None:
    """Create the DB at startup, so it exists (where the app expects it) before the first request."""
    with closing(connect()):
        pass


def consent_state(phone_hash: str) -> str | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT state FROM consent WHERE phone_hash = ?", (phone_hash,)).fetchone()
    return row[0] if row else None


def set_consent(phone_hash: str, state: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO consent (phone_hash, state) VALUES (?, ?) "
            "ON CONFLICT (phone_hash) DO UPDATE SET state = excluded.state, updated_at = CURRENT_TIMESTAMP",
            (phone_hash, state),
        )


def rehash_consent(old: str, new: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE consent SET phone_hash = ? WHERE phone_hash = ?", (new, old))


def incr_reply(keyword: str, template_id: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO reply_counts (keyword, template_id, count) VALUES (?, ?, 1) "
            "ON CONFLICT (keyword, template_id) DO UPDATE SET count = count + 1",
            (keyword, template_id),
        )


def reply_total(keyword: str) -> int:
    """Replies with this keyword, across templates."""
    with closing(connect()) as conn:
        return conn.execute("SELECT COALESCE(SUM(count), 0) FROM reply_counts WHERE keyword = ?",
                            (keyword,)).fetchone()[0]


def inbound_seen(message_id: str) -> bool:
    """True if an inbound text with this id was already processed (survives restarts)."""
    with closing(connect()) as conn:
        return conn.execute("SELECT 1 FROM inbound_seen WHERE message_id = ?", (message_id,)).fetchone() is not None


def mark_inbound_seen(message_id: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("INSERT OR IGNORE INTO inbound_seen (message_id) VALUES (?)", (message_id,))


def add_session(id_hash: str, expires_at: float) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM operator_sessions WHERE expires_at < ?", (time.time(),))
        conn.execute("INSERT INTO operator_sessions (id_hash, expires_at) VALUES (?, ?)", (id_hash, expires_at))


def session_valid(id_hash: str) -> bool:
    with closing(connect()) as conn:
        row = conn.execute("SELECT expires_at FROM operator_sessions WHERE id_hash = ?", (id_hash,)).fetchone()
    return row is not None and row[0] > time.time()


def delete_session(id_hash: str) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM operator_sessions WHERE id_hash = ?", (id_hash,))


def aggregates() -> dict:
    """Everything GET /aggregates serves: reply counts per keyword and template."""
    with closing(connect()) as conn:
        replies = [
            {"keyword": k, "template_id": t, "count": c}
            for k, t, c in conn.execute(
                "SELECT keyword, template_id, count FROM reply_counts ORDER BY keyword, template_id")
        ]
    return {"replies": replies}
