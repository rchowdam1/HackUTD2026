"""Replay ingestion: segment order, ASR/cached switch, fallback, pacing, cancellation.

Whisper is faked here (tests/asr/ runs the real model); each turn's "audio" is a
real file whose name keys the fake transcription.
"""
import asyncio
import json
import time

import pytest

from app import asr, ingest, intent, pipeline
from app.events import hub

SCENARIO_ID = "fixture_otp"
FAKE_DURATION_S = 0.2
# Turn 3 comes back as two whisper segments to check seq numbering across turns.
FAKE_SEGMENTS = {
    "t01.wav": [(0.0, 0.1, "Hi, this is the fraud department at your bank.")],
    "t02.wav": [(0.02, 0.15, "Oh no, what kind of charge?")],
    "t03.wav": [(0.0, 0.08, "A purchase we want to block."), (0.09, 0.18, "I just sent a code.")],
    "t04.wav": [(0.01, 0.19, "Can you read me the code?")],
    "t05.wav": [(0.0, 0.12, "Okay, give me a second.")],
}


@pytest.fixture
def demo(tmp_path, monkeypatch, fixtures_dir):
    """Fake scenarios/demo + audio/demo for the OTP fixture, with a fake whisper."""
    scenario = json.loads((fixtures_dir / "scenario_otp.json").read_text())
    for i, turn in enumerate(scenario["turns"], 1):
        turn["audio"] = f"{SCENARIO_ID}/t{i:02d}.wav"
        wav = tmp_path / "audio" / turn["audio"]
        wav.parent.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(b"")
    (tmp_path / "scenarios" / SCENARIO_ID).mkdir(parents=True)
    (tmp_path / "scenarios" / f"{SCENARIO_ID}.json").write_text(json.dumps(scenario))
    (tmp_path / "scenarios" / SCENARIO_ID / "transcript.json").write_text(
        (fixtures_dir / "scenario_otp" / "transcript.json").read_text())
    monkeypatch.setattr(ingest, "DEMO_DIR", tmp_path / "scenarios")
    monkeypatch.setattr(ingest, "AUDIO_DIR", tmp_path / "audio")
    monkeypatch.setattr(asr, "load_model", lambda: object())
    monkeypatch.setattr(asr, "transcribe", lambda path: (FAKE_SEGMENTS[path.name], FAKE_DURATION_S))
    monkeypatch.delenv("REPLAY_SOURCE", raising=False)
    return scenario


def replay(**kwargs):
    """Run ingest.run; return (session_ref, [(event, monotonic arrival time)], start time)."""
    async def go():
        async with hub.subscribe() as q:
            t0 = time.monotonic()
            task = asyncio.create_task(ingest.run(SCENARIO_ID, **kwargs))
            events = []
            while not task.done() or not q.empty():
                try:
                    events.append((await asyncio.wait_for(q.get(), 0.01), time.monotonic()))
                except asyncio.TimeoutError:
                    pass
            return await task, events, t0
    return asyncio.run(go())


def segments(events):
    return [e.payload for e, _ in events if e.type == "segment"]


def states(events):
    return [e.payload["state"] for e, _ in events if e.type == "session"]


def test_asr_mode_emits_segments_in_order_with_scenario_speakers_and_offsets(demo):
    ref, events, _ = replay(source="asr", realtime=False)
    segs = segments(events)
    assert [s["seq"] for s in segs] == [1, 2, 3, 4, 5, 6]
    assert {s["source"] for s in segs} == {"asr"}
    assert {s["session_ref"] for s in segs} == {ref}
    speakers = [t["speaker"] for t in demo["turns"]]
    assert [s["speaker"] for s in segs] == speakers[:3] + speakers[2:]
    assert [s["text"] for s in segs] == [t for v in FAKE_SEGMENTS.values() for _, _, t in v]
    # cumulative turn offset (200 ms per turn) + whisper segment times
    assert [(s["t_start_ms"], s["t_end_ms"]) for s in segs] == [
        (0, 100), (220, 350), (400, 480), (490, 580), (610, 790), (800, 920)]
    assert states(events) == ["running", "finished"]


def test_cached_mode_replays_transcript(demo, fixtures_dir):
    ref, events, _ = replay(source="cached", realtime=False)
    expected = json.loads((fixtures_dir / "scenario_otp" / "transcript.json").read_text())
    assert segments(events) == [{**line, "session_ref": ref, "source": "cached"} for line in expected]
    assert states(events) == ["running", "finished"]


@pytest.mark.parametrize("env, expected", [(None, "cached"), ("asr", "asr"), ("ASR", "asr"), ("cached", "cached")])
def test_env_switch_picks_default_source(demo, monkeypatch, env, expected):
    if env is not None:
        monkeypatch.setenv("REPLAY_SOURCE", env)
    _, events, _ = replay(realtime=False)
    assert {s["source"] for s in segments(events)} == {expected}


@pytest.mark.parametrize("model_on, arm", [(False, "B"), (True, "C")])
def test_demo_runs_arm_c_when_the_intent_model_is_on(demo, monkeypatch, model_on, arm):
    monkeypatch.setattr(intent, "enabled", lambda: model_on)
    monkeypatch.setattr(intent, "answers", lambda window: None)  # no live calls; C falls back to B per turn
    _, events, _ = replay(source="cached", realtime=False)
    assert {e.payload["arm"] for e, _ in events if e.type == "session"} == {arm}


def test_falls_back_to_cached_when_model_fails_to_load(demo, monkeypatch):
    def broken():
        raise RuntimeError("no model")
    monkeypatch.setattr(asr, "load_model", broken)
    _, events, _ = replay(source="asr", realtime=False)
    assert [s["source"] for s in segments(events)] == ["cached"] * 5
    assert states(events) == ["running", "finished"]


def test_falls_back_to_cached_when_scenario_has_no_audio(demo):
    (ingest.AUDIO_DIR / SCENARIO_ID / "t04.wav").unlink()
    _, events, _ = replay(source="asr", realtime=False)
    assert [s["source"] for s in segments(events)] == ["cached"] * 5


def test_realtime_asr_emits_each_turn_no_earlier_than_its_audio_end(demo):
    _, events, t0 = replay(source="asr", realtime=True)
    seg_events = [(e.payload, at) for e, at in events if e.type == "segment"]
    turn_of_seq = {1: 1, 2: 2, 3: 3, 4: 3, 5: 4, 6: 5}
    for payload, at in seg_events:
        # 30 ms slack: Windows timers tick at ~15.6 ms, so asyncio.sleep can wake a tick early.
        assert at - t0 >= turn_of_seq[payload["seq"]] * FAKE_DURATION_S - 0.03
    assert seg_events[-1][1] - t0 < 5 * FAKE_DURATION_S + 0.5


def test_realtime_cached_paces_each_line_by_its_typing_time(demo, monkeypatch):
    monkeypatch.setattr(ingest, "WORD_MS", 10)
    monkeypatch.setattr(ingest, "TURN_GAP_MS", 20)
    _, events, t0 = replay(source="cached", realtime=True)
    seg_events = [(e.payload, at) for e, at in events if e.type == "segment"]
    expected_at = 0.0
    for payload, at in seg_events:
        # 30 ms slack: Windows timers tick at ~15.6 ms, so asyncio.sleep can wake a tick early.
        assert at - t0 >= expected_at - 0.03
        expected_at += (len(payload["text"].split()) * 10 + 20) / 1000
    assert seg_events[0][1] - t0 < 0.5  # first line starts typing right away


@pytest.mark.parametrize("source", ["asr", "cached"])
def test_reset_mid_replay_stops_without_finish(demo, monkeypatch, source):
    real_process = pipeline.process

    async def process_then_reset(segment):
        out = await real_process(segment)
        if segment.seq == 2:
            await pipeline.reset()
        return out
    monkeypatch.setattr(pipeline, "process", process_then_reset)
    _, events, _ = replay(source=source, realtime=False)
    assert [s["seq"] for s in segments(events)] == [1, 2]
    assert states(events) == ["running", "reset"]


def test_new_session_mid_replay_cancels_old_replay(demo):
    async def go():
        async with hub.subscribe() as q:
            first = asyncio.create_task(ingest.run(SCENARIO_ID, source="asr", realtime=True))
            await asyncio.sleep(FAKE_DURATION_S * 1.5)  # after turn 1 is emitted
            other = await pipeline.start("B", "v1.0", "simulated")
            ref = await first
            return ref, other, [q.get_nowait() for _ in range(q.qsize())]
    ref, other, events = asyncio.run(go())
    assert [e.payload["seq"] for e in events if e.type == "segment"] == [1]
    assert [(e.session_ref, e.payload["state"]) for e in events if e.type == "session"] == [
        (ref, "running"), (ref, "finished"), (other, "running")]  # finished by start(), not by ingest


def test_asr_error_mid_replay_ends_the_call(demo, monkeypatch):
    def transcribe(path):
        if path.name == "t03.wav":
            raise RuntimeError("decoder failed")
        return FAKE_SEGMENTS[path.name], FAKE_DURATION_S
    monkeypatch.setattr(asr, "transcribe", transcribe)
    _, events, _ = replay(source="asr", realtime=False)
    assert [s["seq"] for s in segments(events)] == [1, 2]
    assert states(events) == ["running", "finished"]  # not stranded as "running"
    assert pipeline.current().finished
