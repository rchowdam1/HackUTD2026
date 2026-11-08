"""Photon webhook: POST /sms/inbound receives every event for the project (docs/photon-live.md).

Authenticated by the Standard Webhooks signature (webhook-id/-timestamp/-signature headers, HMAC-SHA256
keyed by PHOTON_WEBHOOK_SECRET), not the operator cookie. Fails closed when the secret is unset.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, HTTPException, Request, Response

from app import sms

router = APIRouter(prefix="/sms")

TOLERANCE_S = 300


def _verify(raw: bytes, headers) -> None:
    secret = os.environ.get("PHOTON_WEBHOOK_SECRET", "")
    event_id, ts = headers.get("webhook-id", ""), headers.get("webhook-timestamp", "")
    if not secret or not ts.isdigit() or abs(time.time() - int(ts)) > TOLERANCE_S:
        raise HTTPException(403, "bad signature")
    key = base64.b64decode(secret.removeprefix("whsec_"))
    expected = base64.b64encode(hmac.new(key, f"{event_id}.{ts}.".encode() + raw, hashlib.sha256).digest()).decode()
    if not any(hmac.compare_digest(expected, s.partition(",")[2]) for s in headers.get("webhook-signature", "").split()):
        raise HTTPException(403, "bad signature")


@router.post("/inbound")
async def inbound(request: Request) -> Response:
    raw = await request.body()
    _verify(raw, request.headers)
    event = json.loads(raw)
    message = event.get("data", {}).get("object", {})
    content = message.get("content", {})
    if event.get("type") == "message.received":
        if content.get("type") == "text":
            await sms.handle_inbound(message.get("id", ""), content.get("text", ""),
                                     message.get("sentBy", {}).get("handle") or None)
    else:
        sms.handle_status(message.get("id", ""), event.get("type", ""))
    return Response(status_code=204)
