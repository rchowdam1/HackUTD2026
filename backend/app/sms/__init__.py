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

from twilio.rest import Client

from app import consent, storage
from app.events import emit
from app.models import ReplyPayload, SmsGateway, SmsMode, SmsPayload
from app.policy import templates

log = logging.getLogger(__name__)
logging.getLogger("twilio.http_client").setLevel(logging.WARNING)

STOP_WORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", "STOP PLEASE", "PLEASE STOP"}

_mode: SmsMode = "simulated"
# Latest alert each recipient was actually sent: recipient (consent._phone) -> (session_ref, ALERT template_id).
# Recorded only after the gateway accepted the alert, so replies never attach to a failed alert.
_last_alerts: dict[str | None, tuple[str, str]] = {}
_sent: dict[str, tuple[str, str | None]] = {}  # Twilio MessageSid -> (template_id, session_ref), for status callbacks


def _check(template_id: str) -> None:
    if not consent.is_active():
        raise RuntimeError("consent not active")
    templates.get(template_id)  # unknown id -> KeyError before anything is sent


def _track(template_id: str, session_ref: str) -> None:
    if template_id.startswith("ALERT-"):
        _last_alerts[consent._phone(None)] = (session_ref, template_id)  # alerts go to DEMO_PHONE


class SimulatedGateway:
    """Records messages for the console phone frame instead of sending them."""

    def __init__(self) -> None:
        self.outbox: list[dict] = []

    def send(self, template_id: str, session_ref: str) -> str:
        _check(template_id)
        message_id = self.deliver(template_id, session_ref=session_ref)
        _track(template_id, session_ref)
        return message_id

    def deliver(self, template_id: str, to: str | None = None, session_ref: str | None = None) -> str:
        message_id = f"SIM{uuid.uuid4().hex[:12]}"
        self.outbox.append({"message_id": message_id, "template_id": template_id, "text": templates.get(template_id)})
        return message_id


class TwilioGateway:
    """Programmable Messaging. Status callbacks go to PUBLIC_BASE_URL/sms/status."""

    def __init__(self) -> None:
        self.client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
        self.from_ = os.environ["TWILIO_FROM"]

    def send(self, template_id: str, session_ref: str) -> str:
        _check(template_id)
        message_id = self.deliver(template_id, session_ref=session_ref)
        _track(template_id, session_ref)
        return message_id

    def deliver(self, template_id: str, to: str | None = None, session_ref: str | None = None) -> str:
        to = to or os.environ["DEMO_PHONE"]
        base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
        extra = {"status_callback": f"{base}/sms/status"} if base else {}
        message = self.client.messages.create(to=to, from_=self.from_, body=templates.get(template_id), **extra)
        _sent[message.sid] = (template_id, session_ref)
        return message.sid


_simulated = SimulatedGateway()
_twilio: TwilioGateway | None = None


def set_mode(mode: SmsMode) -> None:
    global _mode
    _mode = mode


def get_mode() -> SmsMode:
    return _mode


def get_gateway() -> SmsGateway:
    global _twilio
    if _mode == "simulated":
        return _simulated
    if _twilio is None:
        _twilio = TwilioGateway()
    return _twilio


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
    """One inbound text from an enrolled phone (Twilio webhook) or the simulated buttons (phone=None:
    DEMO_PHONE). Duplicate MessageSids are ignored. The id is recorded only after consent and counts
    are stored, so a text whose processing failed (raised) is processed again when Twilio retries.
    Everything up to the record runs without awaiting, so a concurrent duplicate can't interleave."""
    if storage.inbound_seen(message_sid):
        return None
    word = normalise(body)
    alert = _last_alerts.get(consent._phone(phone))
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
    storage.mark_inbound_seen(message_sid)
    wrong_count = sum(r["count"] for r in storage.aggregates()["replies"] if r["keyword"] == "WRONG")
    payload = ReplyPayload(keyword=keyword, counted=counted, wrong_count=wrong_count)
    log.info("sms reply keyword=%s counted=%s", keyword, counted)
    emit("reply", payload, session_ref)

    # After STOP, Twilio blocks sends and replies itself; only the simulated phone shows R-STOP.
    if keyword != "STOP" or get_mode() == "simulated":
        await _reply(template_id, phone, session_ref)
    return payload


def handle_status(message_sid: str, status: str) -> None:
    """Twilio status callback: emit sent/delivered/failed for a message we sent."""
    mapped = {"sent": "sent", "delivered": "delivered", "failed": "failed", "undelivered": "failed"}.get(status)
    if mapped is None or message_sid not in _sent:
        return
    template_id, session_ref = _sent[message_sid]
    emit("sms", SmsPayload(message_id=message_sid, template_id=template_id, status=mapped), session_ref)


async def invite(phone: str | None = None) -> str:
    """Send ENROLL (bypasses the consent check) and mark the phone invited."""
    consent.set_state("invited", phone)
    message_id = await asyncio.to_thread(get_gateway().deliver, "ENROLL", phone)
    emit("sms", SmsPayload(message_id=message_id, template_id="ENROLL", status="queued"), None)
    return message_id
