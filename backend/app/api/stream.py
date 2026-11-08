"""GET /events/stream: SSE relay of the broadcast hub (§19.3). Never touches the work queue.

Each message is `data: <event envelope JSON>`.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.auth import require_operator
from app.events import hub

router = APIRouter(dependencies=[Depends(require_operator)])


async def event_lines() -> AsyncIterator[str]:
    async with hub.subscribe() as q:
        while True:
            event = await q.get()
            yield f"data: {event.model_dump_json()}\n\n"


@router.get("/events/stream")
def stream() -> StreamingResponse:
    return StreamingResponse(event_lines(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
