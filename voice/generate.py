"""Generate the demo call audio with Qwen3-TTS, offline (issue #21).

Setup (once, from the repo root):
    uv venv -p 3.12 voice/.venv && uv pip install -p voice/.venv/bin/python -r voice/requirements.txt
Run (all scenarios, or only the ids given):
    voice/.venv/bin/python voice/generate.py [family ...]
Needs ffmpeg on PATH. Reads scenarios/demo/<id>.json and writes each turn
to audio/demo/<turn.audio> after an 8 kHz mu-law round trip (telephone quality).
Prints per-clip durations; exits non-zero if a scenario exceeds its length limit.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

ROOT = Path(__file__).resolve().parents[1]
MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
VOICES = {"caller": "Ryan", "subscriber": "Aiden"}  # distinct preset English voices
SCENARIO_VOICES = {"family": {"caller": "Aiden", "subscriber": "Serena"}}  # grandson and his grandmother
LIMITS_S = {"clinic": 15.0, "bank": 25.0, "family": 30.0}


def mulaw_roundtrip(src: Path, dst: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        mulaw = Path(tmp) / "mulaw.wav"
        ff = ["ffmpeg", "-y", "-loglevel", "error", "-i"]
        subprocess.run([*ff, str(src), "-ar", "8000", "-ac", "1", "-c:a", "pcm_mulaw", str(mulaw)], check=True)
        subprocess.run([*ff, str(mulaw), "-c:a", "pcm_s16le", str(dst)], check=True)


def main() -> int:
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = Qwen3TTSModel.from_pretrained(MODEL, device_map=device, dtype=torch.float32)
    ok = True
    for scenario_id, limit in LIMITS_S.items():
        if sys.argv[1:] and scenario_id not in sys.argv[1:]:
            continue
        scenario = json.loads((ROOT / "scenarios" / "demo" / f"{scenario_id}.json").read_text())
        total = 0.0
        for turn in scenario["turns"]:
            torch.manual_seed(0)
            wavs, sr = model.generate_custom_voice(text=turn["text"], language="English",
                                                   speaker=SCENARIO_VOICES.get(scenario_id, VOICES)[turn["speaker"]])
            out = ROOT / "audio" / "demo" / turn["audio"]
            out.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as tmp:
                raw = Path(tmp) / "raw.wav"
                sf.write(raw, wavs[0], sr)
                mulaw_roundtrip(raw, out)
            seconds = sf.info(out).duration
            total += seconds
            print(f"{turn['audio']}\t{turn['speaker']}\t{seconds:.2f}s")
        print(f"{scenario_id}\ttotal\t{total:.2f}s (limit {limit:.0f}s)")
        ok &= total <= limit
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
