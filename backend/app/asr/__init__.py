"""ASR: faster-whisper small.en, CPU int8, preloaded at startup (PRD §19.3).

Env `REPLAY_SOURCE` picks the default replay source (app.ingest): `asr` (whisper on the
demo WAVs) or `cached` (scenarios/demo/<id>/transcript.json). Default `cached`, so
pytest and `make smoke` never load a model; the demo sets `REPLAY_SOURCE=asr`.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import BinaryIO, Literal

Source = Literal["asr", "cached"]
MODEL_NAME = "small.en"
log = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()


def default_source() -> Source:
    return "asr" if os.environ.get("REPLAY_SOURCE", "").strip().lower() == "asr" else "cached"


def load_model():
    """Load (once) and return the whisper model. Raises if it can't be loaded."""
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        return _model


def preload() -> None:
    """Load the model at startup when ASR is the default source. Never raises."""
    if default_source() != "asr":
        return
    try:
        load_model()
    except Exception:
        log.exception("ASR model failed to load; replays will use cached transcripts")


def transcribe(audio: Path | BinaryIO) -> tuple[list[tuple[float, float, str]], float]:
    """Blocking. Returns ([(start_s, end_s, text)], audio_duration_s) for a WAV path or in-memory WAV."""
    segments, info = load_model().transcribe(str(audio) if isinstance(audio, Path) else audio, beam_size=5)
    # `segments` is a lazy generator: the decoding happens here, on iteration.
    return [(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()], info.duration
