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

from fastapi import APIRouter, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

from app import consent, sms

log = logging.getLogger(__name__)
router = APIRouter(prefix="/sms", tags=["tunnel"])

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def signed(url: str, params: dict[str, str], signature: str) -> bool:
    """True if Twilio signed this request. False when TWILIO_AUTH_TOKEN or PUBLIC_BASE_URL is unset:
    RequestValidator("") accepts a signature anyone can compute."""
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    return bool(token and sms.public_base_url()) and RequestValidator(token).validate(url, params, signature)


async def verified_form(request: Request) -> dict[str, str]:
    """The form of a Twilio webhook POST signed against PUBLIC_BASE_URL + path, else 403."""
    form = {k: str(v) for k, v in (await request.form()).items()}
    if not signed(sms.public_base_url() + request.url.path, form, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(403, "bad or missing twilio signature")
    return form


@router.post("/inbound")
async def inbound(request: Request) -> Response:
    form = await verified_form(request)
    number = consent.enrolled(form.get("From"))
    if number is None:
        log.warning("inbound text from a missing or unenrolled sender ignored")
    else:
        await sms.handle_inbound(form.get("MessageSid", ""), form.get("Body", ""), number)
    return Response(EMPTY_TWIML, media_type="text/xml")


@router.post("/status")
async def status(request: Request) -> Response:
    form = await verified_form(request)
    sms.handle_status(form.get("MessageSid", ""), form.get("MessageStatus", ""))
    return Response(status_code=204)
