"""Session lifecycle (§19.4). Skeleton stub: a-pipeline replaces the bodies.

Signatures are the contract; callers (ingest, Track B routes) use only these.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app import sms
from app.events import emit
from app.models import Arm, Decision, Segment, SessionPayload, SmsMode, SmsPayload
from app.rules import decide


@dataclass
class _Session:
    ref: str
    generation: int
    arm: Arm
    policy_version: str
    sms_mode: SmsMode
    segments: list[Segment] = field(default_factory=list)
    alerted: list[str] = field(default_factory=list)  # template ids already alerted
    finished: bool = False


_generation = 0
_session: _Session | None = None


def current() -> _Session | None:
    return _session


async def start(arm: Arm, policy_version: str, sms_mode: SmsMode) -> str:
    """Start a session; finishes any active one first. Returns session_ref."""
    global _generation, _session
    if _session is not None and not _session.finished:
        await finish(_session.ref)
    _generation += 1
    _session = _Session(uuid.uuid4().hex[:12], _generation, arm, policy_version, sms_mode)
    emit("session", SessionPayload(state="running", arm=arm, sms_mode=sms_mode), _session.ref, _generation)
    return _session.ref


async def process(segment: Segment) -> list[Decision]:
    """Run decide on all segments so far, publish events, send new alerts.

    decide sees every segment so far and returns the session's decisions;
    only alerts not already seen this session are published and sent.
    """
    s = _session
    if s is None or s.finished or segment.session_ref != s.ref:
        return []  # stale or unknown session: drop
    s.segments.append(segment)
    emit("segment", segment, s.ref, s.generation)
    new = [d for d in decide(s.segments, s.arm, s.policy_version)
           if d.level == "action_warning" and d.template_id and d.template_id not in s.alerted]
    for d in new:
        s.alerted.append(d.template_id)
        emit("decision", d, s.ref, s.generation)
        message_id = sms.get_gateway().send(d.template_id, s.ref)
        emit("sms", SmsPayload(message_id=message_id, template_id=d.template_id, status="queued"),
             s.ref, s.generation)
    return new


async def finish(session_ref: str) -> None:
    """Idempotent. Stub: marks finished, no follow-up SMS yet."""
    s = _session
    if s is None or s.ref != session_ref or s.finished:
        return
    s.finished = True
    emit("session", SessionPayload(state="finished", arm=s.arm, sms_mode=s.sms_mode), s.ref, s.generation)


async def reset() -> None:
    """Invalidate the session and emit reset. Never touches consent."""
    global _generation, _session
    ref = _session.ref if _session else None
    _generation += 1
    _session = None
    emit("session", SessionPayload(state="reset"), ref, _generation)
