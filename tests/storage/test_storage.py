"""SQLite storage (issue #18): counts, aggregates and policy history."""
import sqlite3

import pytest

from app import storage


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "data" / "safesignal.db")
    return storage.DB_PATH


def test_init_creates_tables_idempotently(tmp_db):
    storage.init()
    storage.init()
    with sqlite3.connect(tmp_db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"consent", "reply_counts", "aggregates", "policy_history"} <= tables


def test_incr_reply_returns_running_total_per_keyword():
    assert storage.incr_reply("WRONG", "FU-OTP-01") == 1
    assert storage.incr_reply("WRONG", "FU-OTP-01") == 2
    assert storage.incr_reply("WRONG", "ALERT-OTP-01") == 3
    assert storage.incr_reply("SHARED", "FU-OTP-01") == 1


def test_aggregates_reports_counters_replies_and_policy():
    storage.incr_reply("WRONG", "FU-OTP-01")
    storage.incr("alerts_sent")
    assert storage.incr("alerts_sent") == 2
    storage.record_policy("v1.0", "initial")
    agg = storage.aggregates()
    assert agg["counters"] == {"alerts_sent": 2}
    assert agg["replies"] == [{"keyword": "WRONG", "template_id": "FU-OTP-01", "count": 1}]
    assert [(p["version"], p["note"]) for p in agg["policy_history"]] == [("v1.0", "initial")]


def test_aggregates_empty_db():
    assert storage.aggregates() == {"counters": {}, "replies": [], "policy_history": []}
