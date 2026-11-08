"""Dev set (PRD §19.6): 20 scam + 20 benign, >= 10 hard-benign, all categories, text only."""
from pathlib import Path

from app.models import Scenario

ROOT = Path(__file__).resolve().parents[2] / "scenarios"


def load(set_name):
    return {p.stem: Scenario.model_validate_json(p.read_text()) for p in sorted((ROOT / set_name).glob("*.json"))}


def test_dev_set_shape():
    dev = load("dev")
    assert all(s.id == sid and s.set == "dev" for sid, s in dev.items())
    scams = [s for s in dev.values() if s.label == "scam"]
    benign = [s for s in dev.values() if s.label == "benign"]
    assert (len(scams), len(benign)) == (20, 20)
    assert sum(s.hard_benign for s in benign) >= 10
    assert not any(s.hard_benign for s in scams)
    assert {s.category for s in scams} == {"otp", "payment", "remote"}
    assert {s.category for s in benign} == {"none"}
    assert all(t.audio is None for s in dev.values() for t in s.turns)


def test_dev_set_differs_from_demo():
    demo_lines = {t.text for s in load("demo").values() for t in s.turns}
    assert not demo_lines & {t.text for s in load("dev").values() for t in s.turns}
