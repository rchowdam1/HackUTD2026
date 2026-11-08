"""Session lifecycle (§19.4).

Signatures are the contract; callers (ingest, Track B routes) use only these.

Every session carries a generation number. start() and reset() bump the
global generation; events and SMS send tasks from an older generation are
dropped and never send SMS (§19.10 "late events after reset").

Arm C may run the intent model, so its rules run in a worker thread; the
session lock keeps evaluations in order and makes finish wait for them.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel

from app import consent, intent, rules, sms
from app.events import emit
from app.models import Arm, Decision, EventType, Segment, SessionPayload, SmsMode, SmsPayload

log = logging.getLogger(__name__)


@dataclass
class _Session:
    ref: str
    generation: int
    arm: Arm
    policy_version: str
    sms_mode: SmsMode
    segments: list[Segment] = field(default_factory=list)
    risk_keys: set[tuple] = field(default_factory=set)  # risk events already published
    alerts: list[Decision] = field(default_factory=list)  # action warnings already sent, in order
    tasks: set[asyncio.Task] = field(default_factory=set)  # pending SMS sends
    finished: bool = False  # closed to new segments (set as soon as finish starts)
    finish_task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # held while rules run


_generation = 0
_session: _Session | None = None


def current() -> _Session | None:
    return _session


def current_ref() -> str | None:
    return _session.ref if _session else None


def _live(generation: int) -> bool:
    return generation == _generation


def _emit(s: _Session, type: EventType, payload: BaseModel) -> None:
    if _live(s.generation):
        emit(type, payload, s.ref, s.generation)


async def start(arm: Arm, policy_version: str, sms_mode: SmsMode) -> str:
    """Start a session; finishes any active one first. Returns session_ref."""
    global _generation, _session
    if _session is not None:
        await finish(_session.ref)
    _generation += 1
    _session = _Session(uuid.uuid4().hex[:12], _generation, arm, policy_version, sms_mode)
    _emit(_session, "session", SessionPayload(state="running", arm=arm, sms_mode=sms_mode))
    return _session.ref


async def process(segment: Segment) -> list[Decision]:
    """Run detect/decide on all segments so far, publish what's new, queue new alerts.

    The rules return cumulative results; risk events are diffed by
    (rule_id, event_type, category, span_seq) and alerts by template_id.
    Returns the new action warnings. Segments for a stale, unknown or finished
    session are dropped.
    """
    s = _session
    if s is None or s.finished or segment.session_ref != s.ref:
        return []
    s.segments.append(segment)
    _emit(s, "segment", segment)

    async with s.lock:
        if s.arm == "C":  # the intent model blocks: keep it off the event loop
            events, decisions = await asyncio.to_thread(rules.evaluate, list(s.segments), s.arm, s.policy_version)
            if not _live(s.generation):  # reset during inference
                intent.clear_cache()
                return []
        else:
            events, decisions = rules.evaluate(s.segments, s.arm, s.policy_version)

        for ev in events:
            key = (ev.rule_id, ev.event_type, ev.category, tuple(ev.span_seq))
            if key not in s.risk_keys:
                s.risk_keys.add(key)
                _emit(s, "risk_event", ev)

        sent = {d.template_id for d in s.alerts}
        new = [d for d in decisions if d.level == "action_warning" and d.template_id and d.template_id not in sent]
        for d in new:
            s.alerts.append(d)
            _emit(s, "decision", d)
            _queue_send(s, d.template_id)
        return new


def _queue_send(s: _Session, template_id: str) -> asyncio.Task:
    task = asyncio.create_task(_send(s, template_id))
    s.tasks.add(task)
    task.add_done_callback(s.tasks.discard)
    return task


async def _send(s: _Session, template_id: str) -> None:
    """Send one template in a worker thread (Twilio blocks). Stale generations never send.
    Opted out (consent not active) is a clean skip: no gateway call, no sms event."""
    def send_if_live() -> str | None:
        if not _live(s.generation):
            return None
        if not consent.is_active():
            log.info("sms skipped, consent not active template=%s session=%s", template_id, s.ref)
            return None
        return sms.get_gateway().send(template_id, s.ref)

    try:
        message_id = await asyncio.to_thread(send_if_live)
    except Exception:
        log.exception("sms send failed template=%s session=%s", template_id, s.ref)
        _emit(s, "sms", SmsPayload(message_id="", template_id=template_id, status="failed"))
        return
    if message_id is not None:
        _emit(s, "sms", SmsPayload(message_id=message_id, template_id=template_id, status="queued"))


async def finish(session_ref: str) -> None:
    """Idempotent: repeated or concurrent calls share one finish, so at most one follow-up."""
    s = _session
    if s is None or s.ref != session_ref:
        return
    if s.finish_task is None:
        s.finished = True
        s.finish_task = asyncio.create_task(_finish(s))
    await asyncio.shield(s.finish_task)


async def _finish(s: _Session) -> None:
    async with s.lock:
        intent.clear_cache()
        s.segments.clear()  # call text is transient (PRD §12): gone once the call ends
    await asyncio.gather(*s.tasks, return_exceptions=True)
    if not _live(s.generation):
        return
    first = s.alerts[0] if s.alerts else None
    if first and first.followup_template_id and consent.is_active():
        await asyncio.gather(_queue_send(s, first.followup_template_id), return_exceptions=True)
    _emit(s, "session", SessionPayload(state="finished", arm=s.arm, sms_mode=s.sms_mode))


async def reset() -> None:
    """Cancel pending sends, invalidate the session and emit reset. Never touches consent."""
    global _generation, _session
    s = _session
    _generation += 1
    _session = None
    intent.clear_cache()
    if s is not None:
        s.segments.clear()
        for task in list(s.tasks):
            task.cancel()
    emit("session", SessionPayload(state="reset"), s.ref if s else None, _generation)
