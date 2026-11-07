"""ASR. Skeleton stub: reads the cached transcript instead of running whisper.

a-ingest-asr replaces this with faster-whisper small.en (CPU int8, preloaded).
"""
from __future__ import annotations

import json
from pathlib import Path

from app.models import TranscriptLine


def preload() -> None:
    """Load the model at startup. Stub: nothing to load."""


def load_transcript(path: Path) -> list[TranscriptLine]:
    return [TranscriptLine.model_validate(x) for x in json.loads(Path(path).read_text())]
