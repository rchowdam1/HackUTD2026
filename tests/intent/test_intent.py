"""app.intent and arm C. Minimal pairs written for these tests (not from any scenario file).

The hypotheses and bands were picked on the CASES below, so they check behaviour,
they don't measure accuracy. Real-model tests skip unless the [intent] extra is
installed and the model is in the local HF cache.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from app import intent
from app.models import Scenario, Segment
from app.rules import decide

V = "v1.0"
DEMO = Path(__file__).resolve().parents[2] / "scenarios" / "demo"


def call(*turns):
    """turns: plain strings are the caller; ("subscriber", text) tuples are the subscriber."""
    return [Segment(seq=i, speaker=t[0] if isinstance(t, tuple) else "caller",
                    text=t[1] if isinstance(t, tuple) else t, source="script")
            for i, t in enumerate(turns, 1)]


def alerts(segments, arm):
    return [d.template_id for d in decide(segments, arm, V)]


# Caller turns with a lexicon term that arm B doesn't treat as a request.
SCAMS = {
    "family bail, no payment verb": ("ALERT-PAY-01", call(
        "Grandma, it's me. I got in trouble and I'm at the police station.",
        ("subscriber", "Oh my goodness, are you okay?"),
        "I need help with bail today. Please don't tell Mom.")),
    "bail in gift cards, help me out": ("ALERT-PAY-01", call(
        "Grandpa, the lawyer says bail is fifteen hundred and they only take gift cards. Can you help me out, quick?")),
    "code, need that from you": ("ALERT-OTP-01", call(
        "This is your bank's security department.",
        "The system will text you a code. I'm going to need that from you to verify.")),
    "remote support walkthrough": ("ALERT-REMOTE-01", call(
        "Your computer is sending us virus alerts.",
        "I'll walk you through getting remote support set up so our technician can fix it.")),
}
BENIGN = {
    "never ask for pin": call("Quick reminder from your credit union.",
                              "We will never call and ask for your PIN. If someone does, hang up."),
    "temporary password": call("We emailed you a temporary password; you can change it after you log in."),
    "remote desk closed": call("Our remote support desk is closed on weekends, so please bring the laptop to the store."),
    "bail already handled": call("Hi Grandma, just an update. My lawyer already took care of bail for my friend, "
                                 "nothing you need to do."),
    "gift card balance": call("Thanks for calling. Your gift card balance is fifty dollars."),
}


# --- Without the model (always run) -----------------------------------------

def test_off_by_default_abstains(monkeypatch):
    monkeypatch.delenv("INTENT_MODEL", raising=False)
    assert not intent.enabled()
    (_, segs) = SCAMS["family bail, no payment verb"]
    assert intent.classify(segs) is None
    assert decide(segs, "C", V) == decide(segs, "B", V) == []


def test_broken_model_degrades_to_b(monkeypatch):
    monkeypatch.setattr(intent, "enabled", lambda: True)
    monkeypatch.setattr(intent, "_failed", False)
    monkeypatch.setattr(intent, "load_model", lambda: (_ for _ in ()).throw(OSError("no model")))
    intent._evidence.cache_clear()
    (_, segs) = SCAMS["family bail, no payment verb"]
    assert intent.classify(segs) is None
    assert decide(segs, "C", V) == decide(segs, "B", V)


@pytest.mark.parametrize("scores, expected, category", [
    ((0.95, 0.10, 0.00, 0.00), ("credential_or_code_request", "high"), "otp"),
    ((0.00, 0.75, 0.00, 0.98), ("payment_or_transfer_request", "medium"), "payment"),  # action beats authority
    ((0.00, 0.20, 0.00, 0.96), ("authority_or_relationship_claim_with_urgency", "high"), None),
    ((0.00, 0.50, 0.00, 0.00), ("abstain", "low"), None),
    ((0.05, 0.25, 0.00, 0.00), ("none", "medium"), None),
    ((0.01, 0.02, 0.00, 0.05), ("none", "high"), None),
])
def test_bands(monkeypatch, scores, expected, category):
    monkeypatch.setattr(intent, "enabled", lambda: True)
    monkeypatch.setattr(intent, "_failed", False)
    monkeypatch.setattr(intent, "_scores", lambda premise: dict(zip(intent.HYPOTHESES, scores)))
    intent._evidence.cache_clear()
    segs = call("anything")
    assert intent.evidence(segs) == expected
    assert intent.classify(segs) == category
    intent._evidence.cache_clear()


def test_window_text_has_speakers(monkeypatch):
    seen = []
    monkeypatch.setattr(intent, "_scores", lambda premise: seen.append(premise) or dict.fromkeys(intent.HYPOTHESES, 0.0))
    intent._evidence.cache_clear()
    intent.evidence(call("Hi.", ("subscriber", "Hello?")))
    assert seen == ["Caller: Hi.\nSubscriber: Hello?"]
    intent._evidence.cache_clear()


# --- Real model --------------------------------------------------------------

@pytest.fixture(scope="module")
def model():
    if not all(importlib.util.find_spec(m) for m in ("torch", "transformers")):
        pytest.skip("[intent] extra not installed (uv sync --extra intent)")
    from huggingface_hub import snapshot_download
    try:
        snapshot_download(intent.MODEL, local_files_only=True)
    except Exception:
        pytest.skip(f"{intent.MODEL} not in the local HF cache")
    intent._evidence.cache_clear()
    intent.load_model()
    yield
    intent._evidence.cache_clear()


@pytest.fixture
def on(model, monkeypatch):
    monkeypatch.setenv("INTENT_MODEL", "on")
    monkeypatch.setattr(intent, "_failed", False)


@pytest.mark.parametrize("name", SCAMS)
def test_c_catches_what_b_misses(on, name):
    alert, segs = SCAMS[name]
    assert alerts(segs, "B") == []
    assert alerts(segs, "C") == [alert]
    (d,) = decide(segs, "C", V)
    assert d.basis == [alert.replace("ALERT-", "C-INTENT-")]


@pytest.mark.parametrize("name", BENIGN)
def test_c_stays_silent_on_hard_benign(on, name):
    assert alerts(BENIGN[name], "B") == alerts(BENIGN[name], "C") == []


@pytest.mark.parametrize("scenario_id, expected", [("clinic", []), ("bank", ["ALERT-OTP-01"])])
def test_demo_scenarios(on, scenario_id, expected):
    sc = Scenario.model_validate(json.loads((DEMO / f"{scenario_id}.json").read_text()))
    segs = call(*[t.text if t.speaker == "caller" else ("subscriber", t.text) for t in sc.turns])
    assert alerts(segs, "C") == alerts(segs, "B") == expected
