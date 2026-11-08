"""Live conversation from the console mic (#100).

Two people take turns on one laptop; each recorded turn is transcribed in memory and run through the
pipeline like a replay segment. An alert doesn't end the conversation: End call (POST /demo/end-call)
does, and that is when the follow-up text goes out.
"""
from __future__ import annotations

import asyncio
import io
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app import asr, ingest, pipeline, policy, sms
from app.api.auth import require_operator
from app.api.demo import cancel_replay
from app.models import Segment, Speaker

router = APIRouter(prefix="/live", dependencies=[Depends(require_operator)])
log = logging.getLogger(__name__)

# Turns are transcribed one at a time, in the order they were recorded, so lines keep their order
# even when the next speaker starts before the previous clip has been transcribed.
_turns = asyncio.Lock()


@router.post("/start")
async def start() -> dict:
    cancel_replay()  # a replay still running would keep feeding its lines into the new session
    try:
        await asyncio.to_thread(asr.load_model)  # load now, not on the first turn
    except Exception as e:
        log.exception("ASR model failed to load")
        raise HTTPException(503, "speech recognition unavailable") from e
    ref = await pipeline.start(ingest.arm(), policy.VERSION, sms.get_mode())
    return {"session_ref": ref}


@router.post("/utterance")
async def utterance(speaker: Speaker = Form(...), audio: UploadFile = File(...)) -> dict:
    clip = io.BytesIO(await audio.read())
    async with _turns:
        s = pipeline.current()
        if s is None or s.finished:
            raise HTTPException(409, "no live conversation running")
        try:
            parts, _ = await asyncio.to_thread(asr.transcribe, clip)
        except Exception as e:
            log.exception("ASR failed on a live turn")
            raise HTTPException(422, "could not transcribe that turn") from e
        text = " ".join(t for _, _, t in parts)
        if not text or pipeline.current() is not s or s.finished:  # silence, or the call ended meanwhile
            return {"text": text}
        await pipeline.process(Segment(session_ref=s.ref, seq=len(s.segments) + 1, speaker=speaker, text=text,
                                       source="asr"))
    return {"text": text}
