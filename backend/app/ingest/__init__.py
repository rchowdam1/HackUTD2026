"""Replay ingestion: plays a demo scenario through the pipeline turn by turn.

Track B's `POST /demo/run/{scenario_id}` calls `run(scenario_id, ...)`.
Source `asr` transcribes audio/demo/<id>/tNN.wav with whisper; source `cached`
replays scenarios/demo/<id>/transcript.json. ASR falls back to cached when the
scenario has no audio or the model can't load.

Cancellation is cooperative: a replay stops, without calling finish, as soon as
`pipeline.current()` is None or belongs to another session.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app import asr, pipeline
from app.models import Arm, Scenario, Segment, SmsMode, Speaker

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = REPO_ROOT / "scenarios" / "demo"
AUDIO_DIR = REPO_ROOT / "audio" / "demo"
log = logging.getLogger(__name__)


async def run(
    scenario_id: str,
    *,
    arm: Arm = "B",
    policy_version: str = "v1.0",
    sms_mode: SmsMode = "simulated",
    realtime: bool = True,
    source: asr.Source | None = None,
) -> str:
    """Replay a demo scenario; returns session_ref. `source` defaults to env REPLAY_SOURCE."""
    if (source or asr.default_source()) == "asr":
        turns = await _audio_turns(scenario_id)
        if turns is not None:
            return await _replay_audio(turns, arm=arm, policy_version=policy_version,
                                       sms_mode=sms_mode, realtime=realtime)
    return await replay_transcript(
        DEMO_DIR / scenario_id / "transcript.json",
        arm=arm, policy_version=policy_version, sms_mode=sms_mode, realtime=realtime,
    )


async def replay_transcript(
    path: Path,
    *,
    arm: Arm = "B",
    policy_version: str = "v1.0",
    sms_mode: SmsMode = "simulated",
    realtime: bool = True,
) -> str:
    """Start a session, feed cached segments at their t_end_ms, then finish. Returns session_ref."""
    lines = asr.load_transcript(path)
    ref = await pipeline.start(arm, policy_version, sms_mode)
    t0 = asyncio.get_running_loop().time()
    for line in lines:
        if realtime:
            await _sleep_until(t0, line.t_end_ms)
        if not _alive(ref):
            return ref
        await pipeline.process(Segment(session_ref=ref, source="cached", **line.model_dump()))
    if _alive(ref):
        await pipeline.finish(ref)
    return ref


async def _audio_turns(scenario_id: str) -> list[tuple[Speaker, Path]] | None:
    """(speaker, wav) per turn, or None (logged) if ASR can't run for this scenario."""
    try:
        scenario = Scenario.model_validate_json((DEMO_DIR / f"{scenario_id}.json").read_text())
        turns = [(t.speaker, AUDIO_DIR / t.audio) for t in scenario.turns if t.audio]
        if len(turns) != len(scenario.turns) or not all(p.is_file() for _, p in turns):
            raise FileNotFoundError(f"scenario {scenario_id} is missing turn audio")
        await asyncio.to_thread(asr.load_model)
    except Exception as e:
        log.warning("ASR unavailable for %s (%s); using cached transcript", scenario_id, e)
        return None
    return turns


async def _replay_audio(
    turns: list[tuple[Speaker, Path]], *, arm: Arm, policy_version: str, sms_mode: SmsMode, realtime: bool,
) -> str:
    """Transcribe each turn off the event loop; emit its segments no earlier than the turn's audio end."""
    ref = await pipeline.start(arm, policy_version, sms_mode)
    t0 = asyncio.get_running_loop().time()
    offset_ms = seq = 0
    for speaker, wav in turns:
        segments, duration_s = await asyncio.to_thread(asr.transcribe, wav)
        end_ms = offset_ms + round(duration_s * 1000)
        if realtime:
            await _sleep_until(t0, end_ms)
        for start_s, end_s, text in segments:
            if not _alive(ref):
                return ref
            seq += 1
            await pipeline.process(Segment(
                session_ref=ref, seq=seq, speaker=speaker, text=text, source="asr",
                t_start_ms=offset_ms + round(start_s * 1000), t_end_ms=offset_ms + round(end_s * 1000),
            ))
        offset_ms = end_ms
    if _alive(ref):
        await pipeline.finish(ref)
    return ref


def _alive(ref: str) -> bool:
    s = pipeline.current()
    return s is not None and s.ref == ref


async def _sleep_until(t0: float, offset_ms: int) -> None:
    await asyncio.sleep(max(0.0, t0 + offset_ms / 1000 - asyncio.get_running_loop().time()))
