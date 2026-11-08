"""Demo controls (§19.4): run a replay, end the call, reset, toggle SMS mode."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import ingest, pipeline, sms
from app.api.auth import require_operator
from app.models import SmsMode

router = APIRouter(prefix="/demo", dependencies=[Depends(require_operator)])

_replay: asyncio.Task | None = None


def _cancel_replay() -> None:
    if _replay is not None and not _replay.done():
        _replay.cancel()


@router.post("/run/{scenario_id}", status_code=202)
async def run(scenario_id: str) -> dict:
    global _replay
    if scenario_id not in ingest.scenario_ids():
        raise HTTPException(404, "unknown scenario")
    _cancel_replay()
    mode = sms.get_mode()
    _replay = asyncio.create_task(ingest.run(scenario_id, sms_mode=mode))
    return {"scenario_id": scenario_id, "sms_mode": mode}


@router.post("/end-call")
async def end_call() -> dict:
    _cancel_replay()
    ref = pipeline.current_ref()
    if ref is not None:
        await pipeline.finish(ref)
    return {"status": "ok"}


@router.post("/reset")
async def reset() -> dict:
    _cancel_replay()
    await pipeline.reset()
    return {"status": "ok"}


class Mode(BaseModel):
    mode: SmsMode


@router.post("/sms-mode")
def sms_mode(body: Mode) -> dict:
    sms.set_mode(body.mode)
    return {"mode": sms.get_mode()}
