"""Twilio webhooks: POST /sms/inbound and /sms/status.

Authenticated by X-Twilio-Signature against PUBLIC_BASE_URL + path, not the operator cookie.
Fails closed (403) when TWILIO_AUTH_TOKEN or PUBLIC_BASE_URL is unset.
Only texts from DEMO_PHONE or SPARE_PHONE are handled, and replies go to that configured number,
never to a sender string from the request. Anything else is dropped (empty TwiML, so Twilio doesn't retry).
A 5xx means processing failed and Twilio may retry the same MessageSid.
"""
from __future__ import annotations

import logging
import os
import re

from fastapi import APIRouter, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

from app import sms

log = logging.getLogger(__name__)
router = APIRouter(prefix="/sms")

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def enrolled_number(sender: str | None) -> str | None:
    """The configured DEMO_PHONE / SPARE_PHONE that `sender` is (digits compared), else None."""
    digits = re.sub(r"\D", "", sender or "")
    if not digits:
        return None
    for var in ("DEMO_PHONE", "SPARE_PHONE"):
        number = os.environ.get(var) or ""
        if number and re.sub(r"\D", "", number) == digits:
            return number
    return None


async def _verified_form(request: Request) -> dict[str, str]:
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not token or not base:  # RequestValidator("") accepts a signature anyone can compute
        raise HTTPException(403, "twilio webhook not configured")
    form = {k: str(v) for k, v in (await request.form()).items()}
    if not RequestValidator(token).validate(base + request.url.path, form, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(403, "bad signature")
    return form


@router.post("/inbound")
async def inbound(request: Request) -> Response:
    form = await _verified_form(request)
    number = enrolled_number(form.get("From"))
    if number is None:
        log.warning("inbound text from a missing or unenrolled sender ignored")
    else:
        await sms.handle_inbound(form.get("MessageSid", ""), form.get("Body", ""), number)
    return Response(EMPTY_TWIML, media_type="text/xml")


@router.post("/status")
async def status(request: Request) -> Response:
    form = await _verified_form(request)
    sms.handle_status(form.get("MessageSid", ""), form.get("MessageStatus", ""))
    return Response(status_code=204)
