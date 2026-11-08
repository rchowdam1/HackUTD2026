"""Consent (Track B): the enrolled phones (env DEMO_PHONE, SPARE_PHONE) and each one's state,
stored only as an HMAC keyed by CONSENT_SALT.

Numbers are E.164 strings; `phone=None` means DEMO_PHONE, where alerts go (operator simulation
only: external inbound must come from an `enrolled` sender). A phone with no record is "invited"
(not yet opted in). Every state change emits a `consent` event.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
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


def configured(name: Literal["demo", "spare"]) -> str | None:
    return os.environ.get(f"{name.upper()}_PHONE") or None


def number(phone: str | None) -> str | None:
    return phone or configured("demo")


def enrolled(sender: str | None) -> str | None:
    """The configured DEMO_PHONE / SPARE_PHONE that `sender` is (digits compared), else None."""
    digits = re.sub(r"\D", "", sender or "")
    if not digits:
        return None
    for name in ("demo", "spare"):
        configured_number = configured(name)
        if configured_number and re.sub(r"\D", "", configured_number) == digits:
            return configured_number
    return None


def _stored(phone: str) -> State | None:
    state = storage.consent_state(_hash(phone))
    if state is None:
        state = storage.consent_state(_legacy_hash(phone))
        if state is not None:
            storage.rehash_consent(_legacy_hash(phone), _hash(phone))
    return state


def get_state(phone: str | None = None) -> State:
    n = number(phone)
    return (_stored(n) if n else None) or "invited"


def set_state(state: State, phone: str | None = None) -> None:
    n = number(phone)
    if n is None:
        raise RuntimeError("no phone given and DEMO_PHONE is not set")
    if _stored(n) == state:
        return
    storage.set_consent(_hash(n), state)
    emit("consent", ConsentPayload(state=state), None)


def is_active(phone: str | None = None) -> bool:
    return get_state(phone) == "active"
