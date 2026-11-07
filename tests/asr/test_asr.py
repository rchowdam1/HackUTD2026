"""ASR module. Real-model tests skip cleanly when small.en isn't in the local HF cache.

data/jfk_8k_mulaw.wav: the public-domain JFK clip from the faster-whisper repo
(tests/data/jfk.flac), converted with
`ffmpeg -i jfk.flac -ar 8000 -ac 1 -acodec pcm_mulaw` to mimic the demo audio.
"""
import asyncio
import json
from pathlib import Path

import pytest

from app import asr, ingest

JFK = Path(__file__).parent / "data" / "jfk_8k_mulaw.wav"
JFK_WORDS = "and so my fellow americans ask not what your country can do for you ask what you can do for your country"


def words(text: str) -> str:
    return " ".join("".join(c for c in text.lower() if c.isalpha() or c == " ").split())


@pytest.fixture(scope="module")
def real_model():
    from faster_whisper.utils import download_model
    try:
        download_model(asr.MODEL_NAME, local_files_only=True)
    except Exception:
        pytest.skip("faster-whisper small.en not cached locally")
    return asr.load_model()


@pytest.mark.parametrize("env", [None, "cached", "off"])
def test_preload_is_noop_unless_asr_selected(monkeypatch, env):
    monkeypatch.setattr(asr, "_model", None)
    if env is None:
        monkeypatch.delenv("REPLAY_SOURCE", raising=False)
    else:
        monkeypatch.setenv("REPLAY_SOURCE", env)
    asr.preload()
    assert asr._model is None


def test_preload_never_raises(monkeypatch):
    monkeypatch.setenv("REPLAY_SOURCE", "asr")

    def broken():
        raise RuntimeError("download failed")
    monkeypatch.setattr(asr, "load_model", broken)
    asr.preload()


def test_transcribes_8khz_mulaw_wav(real_model):
    segments, duration_s = asr.transcribe(JFK)
    assert duration_s == pytest.approx(11.0, abs=0.05)
    assert words(" ".join(t for _, _, t in segments)) == JFK_WORDS
    assert all(0 <= s < e <= duration_s + 0.5 for s, e, _ in segments)


def test_asr_replay_of_two_turn_scenario(real_model, tmp_path, monkeypatch):
    """End to end through ingest.run with real whisper: order, speakers, cumulative offsets."""
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "jfk2.json").write_text(json.dumps({
        "id": "jfk2", "set": "demo", "label": "benign", "category": "none",
        "turns": [{"speaker": "caller", "text": "x", "audio": "jfk_8k_mulaw.wav"},
                  {"speaker": "subscriber", "text": "y", "audio": "jfk_8k_mulaw.wav"}],
    }))
    monkeypatch.setattr(ingest, "DEMO_DIR", tmp_path / "demo")
    monkeypatch.setattr(ingest, "AUDIO_DIR", JFK.parent)
    from app.events import hub

    async def go():
        async with hub.subscribe() as q:
            await ingest.run("jfk2", source="asr", realtime=False)
            return [e.payload for e in (q.get_nowait() for _ in range(q.qsize())) if e.type == "segment"]
    segs = asyncio.run(go())
    assert [s["seq"] for s in segs] == list(range(1, len(segs) + 1))
    assert {s["source"] for s in segs} == {"asr"}
    first = [s for s in segs if s["speaker"] == "caller"]
    second = [s for s in segs if s["speaker"] == "subscriber"]
    assert segs == first + second
    assert words(" ".join(s["text"] for s in first)) == words(" ".join(s["text"] for s in second)) == JFK_WORDS
    assert first[-1]["t_end_ms"] <= 11500 and second[0]["t_start_ms"] >= 11000  # second turn offset by clip 1
