"""Demo scenarios (PRD §19.1, §19.4): valid contracts, transcripts match scripts, clip limits."""
from pathlib import Path

import pytest

from app.asr import load_transcript
from app.models import Scenario

DEMO = Path(__file__).resolve().parents[2] / "scenarios" / "demo"
MAX_MS = {"clinic": 15_000, "bank": 25_000}


@pytest.mark.parametrize("sid", sorted(MAX_MS))
def test_demo_scenario(sid):
    scenario = Scenario.model_validate_json((DEMO / f"{sid}.json").read_text())
    lines = load_transcript(DEMO / sid / "transcript.json")
    assert scenario.id == sid and scenario.set == "demo"
    assert [(l.speaker, l.text) for l in lines] == [(t.speaker, t.text) for t in scenario.turns]
    assert [l.seq for l in lines] == list(range(1, len(lines) + 1))
    assert [t.audio for t in scenario.turns] == [f"{sid}/t{i:02d}.wav" for i in range(1, len(lines) + 1)]
    assert lines[-1].t_end_ms <= MAX_MS[sid]


def test_labels():
    clinic = Scenario.model_validate_json((DEMO / "clinic.json").read_text())
    bank = Scenario.model_validate_json((DEMO / "bank.json").read_text())
    assert (clinic.label, clinic.hard_benign, clinic.category) == ("benign", True, "none")
    assert (bank.label, bank.category) == ("scam", "otp")
