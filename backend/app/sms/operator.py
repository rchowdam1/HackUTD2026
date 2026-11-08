"""Operator-only SMS routes for the console (cookie required)."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import consent, sms
from app.api.auth import require_operator
from app.policy import templates

router = APIRouter(prefix="/sms", dependencies=[Depends(require_operator)])


class Inbound(BaseModel):
    body: str


@router.post("/simulate-inbound")
async def simulate_inbound(msg: Inbound) -> dict:
    """Phone-frame buttons: same handler as Twilio inbound, from the demo phone."""
    payload = await sms.handle_inbound(f"SIMIN{uuid.uuid4().hex[:12]}", msg.body)
    return payload.model_dump()


@router.get("/templates/{template_id}")
def template_text(template_id: str) -> dict:
    try:
        return {"template_id": template_id, "text": templates.get(template_id)}
    except KeyError:
        raise HTTPException(404, "unknown template") from None


@router.get("/outbox")
def outbox() -> list[dict]:
    """Messages the simulated gateway has 'sent', oldest first."""
    return sms.simulated.outbox


class Invite(BaseModel):
    phone: Literal["demo", "spare"] = "demo"


@router.post("/invite")
async def invite(body: Invite) -> dict:
    """Send ENROLL to DEMO_PHONE or SPARE_PHONE (chosen by name, so no number crosses the API)."""
    number = consent.configured(body.phone)
    if not number:
        raise HTTPException(400, f"{body.phone.upper()}_PHONE is not set")
    return {"message_id": await sms.invite(number)}
