"""Consent (Track B): state per enrolled phone, stored only as an HMAC keyed by CONSENT_SALT.

Numbers are E.164 strings; `phone=None` means env DEMO_PHONE (operator simulation only:
external inbound must name an enrolled sender, see app.sms.webhooks). A phone with no
record is "invited" (not yet opted in). Every state change emits a `consent` event.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from contextlib import closing
from typing import Literal

from app import storage
from app.events import emit
from app.models import ConsentPayload

State = Literal["invited", "active", "stopped"]


def _salt() -> str:
    salt = os.environ.get("CONSENT_SALT")
    if not salt:
        raise RuntimeError("CONSENT_SALT is not set")
    return salt


def _hash(phone: str) -> str:
    """HMAC-SHA256 keyed by CONSENT_SALT. Keep the salt out of any backup of data/."""
    return hmac.new(_salt().encode(), b"consent-phone:" + phone.encode(), hashlib.sha256).hexdigest()


def _legacy_hash(phone: str) -> str:
    return hashlib.sha256((_salt() + phone).encode()).hexdigest()  # before HMAC; migrated on first read


def _phone(phone: str | None) -> str | None:
    return phone or os.environ.get("DEMO_PHONE") or None


def _stored(number: str) -> State | None:
    with closing(storage.connect()) as conn, conn:
        row = conn.execute("SELECT state FROM consent WHERE phone_hash = ?", (_hash(number),)).fetchone()
        if row is None:
            row = conn.execute("SELECT state FROM consent WHERE phone_hash = ?", (_legacy_hash(number),)).fetchone()
            if row is not None:
                conn.execute("UPDATE consent SET phone_hash = ? WHERE phone_hash = ?",
                             (_hash(number), _legacy_hash(number)))
    return row[0] if row else None


def get_state(phone: str | None = None) -> State:
    number = _phone(phone)
    return (_stored(number) if number else None) or "invited"


def set_state(state: State, phone: str | None = None) -> None:
    number = _phone(phone)
    if number is None:
        raise RuntimeError("no phone given and DEMO_PHONE is not set")
    if _stored(number) == state:
        return
    with closing(storage.connect()) as conn, conn:
        conn.execute(
            "INSERT INTO consent (phone_hash, state) VALUES (?, ?) "
            "ON CONFLICT (phone_hash) DO UPDATE SET state = excluded.state, updated_at = CURRENT_TIMESTAMP",
            (_hash(number), state),
        )
    emit("consent", ConsentPayload(state=state), None)


def is_active(phone: str | None = None) -> bool:
    return get_state(phone) == "active"
