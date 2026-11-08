"""Photon bridge inbound: POST /sms/inbound {id, text, sender} from the Spectrum bridge (hackutd/).

Authenticated by x-bridge-token == PHOTON_BRIDGE_TOKEN, not the operator cookie. Fails closed when unset.
"""
from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel

from app import sms

router = APIRouter(prefix="/sms")


class BridgeInbound(BaseModel):
    id: str
    text: str
    sender: str | None = None


@router.post("/inbound")
async def inbound(msg: BridgeInbound, x_bridge_token: str = Header("")) -> Response:
    token = os.environ.get("PHOTON_BRIDGE_TOKEN", "")
    if not token or not hmac.compare_digest(x_bridge_token, token):
        raise HTTPException(403, "bad bridge token")
    await sms.handle_inbound(msg.id, msg.text, msg.sender)
    return Response(status_code=204)
