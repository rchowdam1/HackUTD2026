"""Broadcast hub: fans events out to SSE subscribers.

Separate from pipeline work: subscribers each get their own queue and never
consume pipeline tasks (§19.3).
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pydantic import BaseModel

from app.models import Event, EventType


class Hub:
    def __init__(self, maxsize: int = 1000) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._maxsize = maxsize

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event]]:
        q: asyncio.Queue[Event] = asyncio.Queue(self._maxsize)
        self._subscribers.add(q)
        try:
            yield q
        finally:
            self._subscribers.discard(q)

    def publish(self, event: Event) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # a slow console drops events rather than blocking the pipeline


hub = Hub()


def emit(type: EventType, payload: BaseModel, session_ref: str | None, generation: int = 0) -> Event:
    event = Event(
        event_id=uuid.uuid4().hex,
        session_ref=session_ref,
        type=type,
        payload=payload.model_dump(mode="json"),
        generation=generation,
    )
    hub.publish(event)
    return event
