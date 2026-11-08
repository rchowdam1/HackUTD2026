"""Consent (Track B): state per enrolled phone, stored only as a salted SHA-256.

Numbers are E.164 strings; `phone=None` means env DEMO_PHONE. A phone with no
record is "invited" (not yet opted in). Every state change emits a `consent` event.
"""
from __future__ import annotations

import hashlib
import os
from contextlib import closing
from typing import Literal

from app import storage
from app.events import emit
from app.models import ConsentPayload

State = Literal["invited", "active", "stopped"]


def _hash(phone: str) -> str:
    salt = os.environ.get("CONSENT_SALT")
    if not salt:
        raise RuntimeError("CONSENT_SALT is not set")
    return hashlib.sha256((salt + phone).encode()).hexdigest()


def _phone(phone: str | None) -> str | None:
    return phone or os.environ.get("DEMO_PHONE") or None


def _stored(number: str) -> State | None:
    with closing(storage.connect()) as conn:
        row = conn.execute("SELECT state FROM consent WHERE phone_hash = ?", (_hash(number),)).fetchone()
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
