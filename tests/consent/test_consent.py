"""Consent (issue #18): stored state transitions, hashed numbers only, consent events."""
import asyncio
import logging
import sqlite3

import pytest

from app import consent, pipeline, storage

DEMO = "+15551234567"
SPARE = "+15557654321"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "data" / "safesignal.db")
    monkeypatch.setenv("CONSENT_SALT", "test-salt")
    monkeypatch.setenv("DEMO_PHONE", DEMO)
    monkeypatch.setenv("SPARE_PHONE", SPARE)


@pytest.fixture
def events(monkeypatch):
    seen = []
    monkeypatch.setattr(consent, "emit", lambda type, payload, ref: seen.append((type, payload.state, ref)))
    return seen


def stored_rows():
    with sqlite3.connect(storage.DB_PATH) as conn:
        return conn.execute("SELECT phone_hash, state FROM consent").fetchall()


def test_unknown_phone_is_invited():
    assert consent.get_state() == "invited"
    assert not consent.is_active()


def test_state_transitions_are_stored(events):
    for state in ["invited", "active", "stopped", "active"]:
        consent.set_state(state)
        assert consent.get_state() == state
        assert stored_rows()[0][1] == state
    assert consent.is_active()
    assert len(stored_rows()) == 1


def test_consent_event_only_on_change(events):
    consent.set_state("active")
    consent.set_state("active")
    consent.set_state("stopped")
    assert events == [("consent", "active", None), ("consent", "stopped", None)]


def test_none_means_demo_phone_and_spare_is_separate(events):
    consent.set_state("active")
    assert consent.get_state(DEMO) == "active"
    assert consent.get_state(SPARE) == "invited"
    consent.set_state("active", SPARE)
    assert consent.get_state(SPARE) == "active"
    assert len(stored_rows()) == 2


def test_no_raw_number_in_database_or_logs(events, caplog):
    caplog.set_level(logging.DEBUG)
    consent.set_state("active")
    consent.set_state("stopped", SPARE)
    consent.get_state(SPARE)
    storage.incr_reply("WRONG", "FU-OTP-01")
    raw = storage.DB_PATH.read_bytes()
    for number in (DEMO, SPARE):
        digits = number.lstrip("+")
        assert digits.encode() not in raw
        assert digits[-10:].encode() not in raw
        assert digits not in caplog.text
    for phone_hash, _ in stored_rows():
        assert len(phone_hash) == 64 and DEMO not in phone_hash


def test_hash_is_salted(monkeypatch, events):
    consent.set_state("active")
    first = stored_rows()[0][0]
    monkeypatch.setenv("CONSENT_SALT", "other-salt")
    assert consent.get_state() == "invited"
    consent.set_state("active")
    assert first != consent._hash(DEMO)


def test_missing_salt_or_phone_refuses(monkeypatch):
    monkeypatch.delenv("CONSENT_SALT")
    with pytest.raises(RuntimeError):
        consent.set_state("active")
    monkeypatch.setenv("CONSENT_SALT", "s")
    monkeypatch.delenv("DEMO_PHONE")
    with pytest.raises(RuntimeError):
        consent.set_state("active")
    assert consent.get_state() == "invited"


def test_reset_keeps_consent_and_aggregates(events):
    consent.set_state("active")
    storage.incr_reply("WRONG", "FU-OTP-01")
    asyncio.run(pipeline.reset())
    assert consent.is_active()
    assert storage.aggregates()["replies"][0]["count"] == 1


def test_hash_is_hmac_and_legacy_rows_migrate(events):
    import hashlib
    from contextlib import closing
    legacy = hashlib.sha256(("test-salt" + DEMO).encode()).hexdigest()
    assert consent._hash(DEMO) != legacy
    with closing(storage.connect()) as conn, conn:
        conn.execute("INSERT INTO consent (phone_hash, state) VALUES (?, 'active')", (legacy,))
    assert consent.get_state() == "active"  # an enrolled phone survives the upgrade
    assert stored_rows() == [(consent._hash(DEMO), "active")]
