"""Photon bridge inbound: POST /sms/inbound {id, text, sender} from the Spectrum bridge (hackutd/).

Authenticated by x-bridge-token == PHOTON_BRIDGE_TOKEN, not the operator cookie. Fails closed when unset.
Only texts from DEMO_PHONE or SPARE_PHONE are handled, and replies go to that configured number,
never to a sender string from the request. Anything else is dropped (204, so the bridge doesn't retry).
A 5xx means processing failed and the bridge should retry the same message id.
"""
from __future__ import annotations

import hmac
import logging
import os
import re

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel

from app import sms

log = logging.getLogger(__name__)
router = APIRouter(prefix="/sms")


class BridgeInbound(BaseModel):
    id: str
    text: str
    sender: str | None = None


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


@router.post("/inbound")
async def inbound(msg: BridgeInbound, x_bridge_token: str = Header("")) -> Response:
    token = os.environ.get("PHOTON_BRIDGE_TOKEN", "")
    if not token or not hmac.compare_digest(x_bridge_token, token):
        raise HTTPException(403, "bad bridge token")
    number = enrolled_number(msg.sender)
    if number is None:
        log.warning("inbound text from a missing or unenrolled sender ignored")
        return Response(status_code=204)
    await sms.handle_inbound(msg.id, msg.text, number)
    return Response(status_code=204)
