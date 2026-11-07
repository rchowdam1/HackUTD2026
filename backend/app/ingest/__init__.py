"""Replay ingestion. Skeleton stub: cached-transcript replay only.

Track B's `POST /demo/run/{scenario_id}` calls `run(scenario_id, ...)`.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app import asr, pipeline
from app.models import Arm, Segment, SmsMode

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = REPO_ROOT / "scenarios" / "demo"


async def run(
    scenario_id: str,
    *,
    arm: Arm = "B",
    policy_version: str = "v1.0",
    sms_mode: SmsMode = "simulated",
    realtime: bool = True,
) -> str:
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
    """Start a session, feed segments at their timestamps, then finish. Returns session_ref."""
    lines = asr.load_transcript(path)
    ref = await pipeline.start(arm, policy_version, sms_mode)
    elapsed_ms = 0
    for line in lines:
        if realtime and line.t_end_ms > elapsed_ms:
            await asyncio.sleep((line.t_end_ms - elapsed_ms) / 1000)
            elapsed_ms = line.t_end_ms
        await pipeline.process(Segment(session_ref=ref, source="cached", **line.model_dump()))
    await pipeline.finish(ref)
    return ref
