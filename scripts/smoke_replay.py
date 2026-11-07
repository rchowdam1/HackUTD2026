"""Replay the A-owned OTP fixture through the pipeline and print every event.

Usage: uv run python scripts/smoke_replay.py [--realtime]
Exits non-zero if segments are missing or out of order.
"""
import asyncio
import sys
from pathlib import Path

from app import ingest
from app.events import hub

TRANSCRIPT = Path(__file__).resolve().parents[1] / "tests/fixtures/scenario_otp/transcript.json"


async def main(realtime: bool) -> int:
    async with hub.subscribe() as q:
        ref = await ingest.replay_transcript(TRANSCRIPT, realtime=realtime)
        events = [q.get_nowait() for _ in range(q.qsize())]
    for e in events:
        print(e.type, e.payload)
    seqs = [e.payload["seq"] for e in events if e.type == "segment"]
    states = [e.payload["state"] for e in events if e.type == "session"]
    ok = seqs == [1, 2, 3, 4, 5] and states == ["running", "finished"] and all(e.session_ref == ref for e in events)
    print("SMOKE REPLAY", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--realtime" in sys.argv)))
