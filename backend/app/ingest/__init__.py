"""Replay ingestion: plays a demo scenario through the pipeline turn by turn.

Track B's `POST /demo/run/{scenario_id}` calls `run(scenario_id, ...)`.
Source `asr` transcribes audio/demo/<id>/tNN.wav with whisper; source `cached`
replays scenarios/demo/<id>/transcript.json. ASR falls back to cached when the
scenario has no audio or the model can't load.

Cancellation is cooperative: a replay stops, without calling finish, as soon as
another session (or none) is current.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from app import ROOT, asr, pipeline, policy
from app.models import Scenario, Segment, SmsMode, Speaker, TranscriptLine

DEMO_DIR = ROOT / "scenarios" / "demo"
AUDIO_DIR = ROOT / "audio" / "demo"
log = logging.getLogger(__name__)

# (ms into the call the segment is due, Segment fields except session_ref)
Timed = AsyncIterator[tuple[int, dict]]


def scenario_ids() -> set[str]:
    return {p.stem for p in DEMO_DIR.glob("*.json")}


def load_transcript(path: Path) -> list[TranscriptLine]:
    return [TranscriptLine.model_validate(x) for x in json.loads(Path(path).read_text())]


def audio_turns(scenario_id: str) -> list[tuple[Speaker, Path]] | None:
    """(speaker, wav) per turn, or None if any turn has no audio file."""
    scenario = Scenario.model_validate_json((DEMO_DIR / f"{scenario_id}.json").read_text())
    turns = [(t.speaker, AUDIO_DIR / t.audio) for t in scenario.turns if t.audio]
    if len(turns) != len(scenario.turns) or not all(p.is_file() for _, p in turns):
        return None
    return turns


async def run(
    scenario_id: str,
    *,
    sms_mode: SmsMode = "simulated",
    realtime: bool = True,
    source: asr.Source | None = None,
) -> str:
    """Replay a demo scenario; returns session_ref. `source` defaults to env REPLAY_SOURCE."""
    turns = await _asr_turns(scenario_id) if (source or asr.default_source()) == "asr" else None
    segments = _transcribed(turns) if turns else _cached(load_transcript(DEMO_DIR / scenario_id / "transcript.json"))
    return await _replay(segments, sms_mode, realtime)


async def replay_transcript(
    path: Path,
    *,
    sms_mode: SmsMode = "simulated",
    realtime: bool = True,
) -> str:
    """Replay a cached transcript file; returns session_ref."""
    return await _replay(_cached(load_transcript(path)), sms_mode, realtime)


async def _replay(segments: Timed, sms_mode: SmsMode, realtime: bool) -> str:
    """Start an arm B session, feed each segment no earlier than it is due, then finish."""
    ref = await pipeline.start("B", policy.VERSION, sms_mode)
    t0 = asyncio.get_running_loop().time()
    async for due_ms, fields in segments:
        if realtime:
            await asyncio.sleep(max(0.0, t0 + due_ms / 1000 - asyncio.get_running_loop().time()))
        if not _alive(ref):
            return ref
        await pipeline.process(Segment(session_ref=ref, **fields))
    if _alive(ref):
        await pipeline.finish(ref)
    return ref


async def _cached(lines: list[TranscriptLine]) -> Timed:
    for line in lines:
        yield line.t_end_ms, {"source": "cached", **line.model_dump()}


async def _asr_turns(scenario_id: str) -> list[tuple[Speaker, Path]] | None:
    """audio_turns() once the model is loaded, or None (logged) if ASR can't run for this scenario."""
    try:
        turns = audio_turns(scenario_id)
        if turns is None:
            raise FileNotFoundError(f"scenario {scenario_id} is missing turn audio")
        await asyncio.to_thread(asr.load_model)
    except Exception as e:
        log.warning("ASR unavailable for %s (%s); using cached transcript", scenario_id, e)
        return None
    return turns


async def _transcribed(turns: list[tuple[Speaker, Path]]) -> Timed:
    """Transcribe each turn off the event loop; its segments are due at the turn's audio end.
    A transcription error ends the source, so the call finishes on the segments so far."""
    offset_ms = seq = 0
    for speaker, wav in turns:
        try:
            segments, duration_s = await asyncio.to_thread(asr.transcribe, wav)
        except Exception:
            log.exception("ASR failed mid-replay; ending the call")
            return
        end_ms = offset_ms + round(duration_s * 1000)
        for start_s, end_s, text in segments:
            seq += 1
            yield end_ms, {"seq": seq, "speaker": speaker, "text": text, "source": "asr",
                           "t_start_ms": offset_ms + round(start_s * 1000),
                           "t_end_ms": offset_ms + round(end_s * 1000)}
        offset_ms = end_ms


def _alive(ref: str) -> bool:
    return pipeline.current_ref() == ref
