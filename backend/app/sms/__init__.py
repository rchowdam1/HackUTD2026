"""SMS gateways and reply keywords (Track B, §19.3–§19.4).

`get_gateway()` returns the gateway for the current mode (`set_mode`/`get_mode`).
`send()` is the consent-checked path the pipeline uses; `deliver()` sends without
the check, for keyword replies and the ENROLL invite. Never log numbers or bodies.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid

import httpx

from app import consent, storage
from app.events import emit
from app.models import ReplyPayload, SmsGateway, SmsMode, SmsPayload
from app.policy import templates

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "STOP PLEASE", "PLEASE STOP"}

_mode: SmsMode = "simulated"
_last_alert: tuple[str, str] | None = None  # (session_ref, ALERT template_id) of the latest alert sent
_seen_sids: set[str] = set()


def _check_and_track(template_id: str, session_ref: str) -> None:
    global _last_alert
    if not consent.is_active():
        raise RuntimeError("consent not active")
    templates.get(template_id)  # unknown id -> KeyError before anything is sent
    if template_id.startswith("ALERT-"):
        _last_alert = (session_ref, template_id)


class SimulatedGateway:
    """Records messages for the console phone frame instead of sending them."""

    def __init__(self) -> None:
        self.outbox: list[dict] = []

    def send(self, template_id: str, session_ref: str) -> str:
        _check_and_track(template_id, session_ref)
        return self.deliver(template_id, session_ref=session_ref)

    def deliver(self, template_id: str, to: str | None = None, session_ref: str | None = None) -> str:
        message_id = f"SIM{uuid.uuid4().hex[:12]}"
        self.outbox.append({"message_id": message_id, "template_id": template_id, "text": templates.get(template_id)})
        return message_id


class PhotonGateway:
    """iMessage through Photon Spectrum, via the local Bun bridge in hackutd/ (docs/photon-live.md).

    Spectrum has no HTTP send API, so the bridge owns the SDK; inbound texts come back on /sms/inbound.
    """

    def __init__(self) -> None:
        self.http = httpx.Client(base_url=os.environ.get("PHOTON_BRIDGE_URL") or "http://127.0.0.1:8787",
                                 headers={"x-bridge-token": os.environ["PHOTON_BRIDGE_TOKEN"]}, timeout=30)

    def send(self, template_id: str, session_ref: str) -> str:
        _check_and_track(template_id, session_ref)
        return self.deliver(template_id, session_ref=session_ref)

    def deliver(self, template_id: str, to: str | None = None, session_ref: str | None = None) -> str:
        response = self.http.post("/send", json={"to": to or os.environ["DEMO_PHONE"], "text": templates.get(template_id)})
        response.raise_for_status()
        return response.json()["id"]


_simulated = SimulatedGateway()
_photon: PhotonGateway | None = None


def set_mode(mode: SmsMode) -> None:
    global _mode
    _mode = mode


def get_mode() -> SmsMode:
    return _mode


def get_gateway() -> SmsGateway:
    global _photon
    if _mode == "simulated":
        return _simulated
    if _photon is None:
        _photon = PhotonGateway()
    return _photon


def normalise(body: str) -> str:
    """Trim, strip punctuation, collapse spaces, upper-case: "Wrong." -> "WRONG"."""
    return " ".join(re.sub(r"[^\w\s]", "", body).split()).upper()


async def _reply(template_id: str, to: str | None, session_ref: str | None) -> None:
    gateway = get_gateway()
    try:
        message_id = await asyncio.to_thread(gateway.deliver, template_id, to, session_ref)
        status = "delivered" if gateway is _simulated else "queued"
    except Exception:
        log.exception("sms reply failed template=%s", template_id)
        message_id, status = "", "failed"
    emit("sms", SmsPayload(message_id=message_id, template_id=template_id, status=status), session_ref)


async def handle_inbound(message_sid: str, body: str, phone: str | None = None) -> ReplyPayload | None:
    """One inbound text (Photon webhook or simulated button). Duplicate message ids are ignored."""
    if message_sid in _seen_sids:
        return None
    _seen_sids.add(message_sid)
    word = normalise(body)
    alert = _last_alert
    session_ref = alert[0] if alert else None

    if word in STOP_WORDS:
        keyword, template_id = "STOP", "R-STOP"
        consent.set_state("stopped", phone)
    elif word in {"START", "YES"}:
        keyword, template_id = word, "R-YES"
        consent.set_state("active", phone)
    elif word == "SHARED" and alert:
        keyword, template_id = "SHARED", templates.shared_for(alert[1])
    elif word == "WRONG":
        keyword, template_id = "WRONG", "R-WRONG"
    else:
        keyword, template_id = "HELP", "R-HELP"

    counted = alert is not None
    if counted:
        storage.incr_reply(keyword, alert[1])
    wrong_count = sum(r["count"] for r in storage.aggregates()["replies"] if r["keyword"] == "WRONG")
    payload = ReplyPayload(keyword=keyword, counted=counted, wrong_count=wrong_count)
    log.info("sms reply keyword=%s counted=%s", keyword, counted)
    emit("reply", payload, session_ref)

    # Photon does no STOP handling of its own, so we confirm R-STOP ourselves in both modes.
    await _reply(template_id, phone, session_ref)
    return payload


async def invite(phone: str | None = None) -> str:
    """Send ENROLL (bypasses the consent check) and mark the phone invited."""
    consent.set_state("invited", phone)
    message_id = await asyncio.to_thread(get_gateway().deliver, "ENROLL", phone)
    emit("sms", SmsPayload(message_id=message_id, template_id="ENROLL", status="queued"), None)
    return message_id
