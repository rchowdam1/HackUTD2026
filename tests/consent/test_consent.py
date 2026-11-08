"""Consent (issue #18): stored state transitions, hashed numbers only, consent events."""
import asyncio
import hashlib
import logging
import sqlite3

import pytest

from app import consent, pipeline, storage

DEMO = "+15551234567"
SPARE = "+15557654321"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("CONSENT_SALT", "test-salt")
    monkeypatch.setenv("DEMO_PHONE", DEMO)
    monkeypatch.setenv("SPARE_PHONE", SPARE)


def stored_rows():
    with sqlite3.connect(storage.DB_PATH) as conn:
        return conn.execute("SELECT phone_hash, state FROM consent").fetchall()


def test_unknown_phone_is_invited():
    assert consent.get_state() == "invited"
    assert not consent.is_active()


def test_state_transitions_are_stored():
    for state in ["invited", "active", "stopped", "active"]:
        consent.set_state(state)
        assert consent.get_state() == state
        assert stored_rows()[0][1] == state
    assert consent.is_active()
    assert len(stored_rows()) == 1


def test_consent_event_only_on_change(published):
    consent.set_state("active")
    consent.set_state("active")
    consent.set_state("stopped")
    assert [(t, p.state, ref) for t, p, ref in published] == [("consent", "active", None), ("consent", "stopped", None)]


def test_none_means_demo_phone_and_spare_is_separate():
    consent.set_state("active")
    assert consent.get_state(DEMO) == "active"
    assert consent.get_state(SPARE) == "invited"
    consent.set_state("active", SPARE)
    assert consent.get_state(SPARE) == "active"
    assert len(stored_rows()) == 2


def test_no_raw_number_in_database_or_logs(caplog):
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
        assert len(phone_hash) == 64


def test_hash_is_salted(monkeypatch):
    consent.set_state("active")
    first = stored_rows()[0][0]
    monkeypatch.setenv("CONSENT_SALT", "other-salt")
    assert consent.get_state() == "invited"
    consent.set_state("active")
    assert first != stored_rows()[1][0]


def test_missing_salt_or_phone_refuses(monkeypatch):
    monkeypatch.delenv("CONSENT_SALT")
    with pytest.raises(RuntimeError):
        consent.set_state("active")
    monkeypatch.setenv("CONSENT_SALT", "s")
    monkeypatch.delenv("DEMO_PHONE")
    with pytest.raises(RuntimeError):
        consent.set_state("active")
    assert consent.get_state() == "invited"


def test_reset_keeps_consent_and_aggregates():
    consent.set_state("active")
    storage.incr_reply("WRONG", "FU-OTP-01")
    asyncio.run(pipeline.reset())
    assert consent.is_active()
    assert storage.aggregates()["replies"][0]["count"] == 1


def test_legacy_rows_migrate():
    legacy = hashlib.sha256(("test-salt" + DEMO).encode()).hexdigest()
    storage.set_consent(legacy, "active")
    assert consent.get_state() == "active"  # an enrolled phone survives the upgrade
    assert [(h == legacy, s) for h, s in stored_rows()] == [(False, "active")]
