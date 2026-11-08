"""GET /events/stream: SSE relay of the broadcast hub (§19.3). Never touches the work queue.

Each message is `data: <event envelope JSON>`.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app import consent, sms, storage
from app.api.auth import require_operator
from app.events import hub

router = APIRouter(dependencies=[Depends(require_operator)])


async def event_lines() -> AsyncIterator[str]:
    async with hub.subscribe() as q:
        # A comment right away: the response headers go out now, so the console's EventSource opens (and
        # reconciles from GET /state) without waiting for the next event.
        yield ": connected\n\n"
        while True:
            event = await q.get()
            yield f"data: {event.model_dump_json()}\n\n"


@router.get("/events/stream")
def stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/state")
def state() -> dict:
    """Snapshot a console loads on every (re)connect, so events it missed are not lost: SMS mode,
    WRONG total, DEMO_PHONE consent, and every event since the latest session start or reset."""
    try:
        consent_state = consent.get_state()
    except RuntimeError:  # CONSENT_SALT unset
        consent_state = None
    wrong = sum(r["count"] for r in storage.aggregates()["replies"] if r["keyword"] == "WRONG")
    return {"sms_mode": sms.get_mode(), "wrong_count": wrong, "consent": consent_state,
            "events": [e.model_dump(mode="json") for e in hub.history]}
