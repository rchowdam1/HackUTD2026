"""Twilio webhooks: POST /sms/inbound and /sms/status.

Authenticated by X-Twilio-Signature against PUBLIC_BASE_URL + path, not the operator cookie.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

from app import sms

router = APIRouter(prefix="/sms")

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


async def _verified_form(request: Request) -> dict[str, str]:
    form = {k: str(v) for k, v in (await request.form()).items()}
    url = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/") + request.url.path
    validator = RequestValidator(os.environ.get("TWILIO_AUTH_TOKEN", ""))
    if not validator.validate(url, form, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(403, "bad signature")
    return form


@router.post("/inbound")
async def inbound(request: Request) -> Response:
    form = await _verified_form(request)
    await sms.handle_inbound(form.get("MessageSid", ""), form.get("Body", ""), form.get("From") or None)
    return Response(EMPTY_TWIML, media_type="text/xml")


@router.post("/status")
async def status(request: Request) -> Response:
    form = await _verified_form(request)
    sms.handle_status(form.get("MessageSid", ""), form.get("MessageStatus", ""))
    return Response(status_code=204)
