"""app.intent (TypeSafe Jev) and arm C, with mocked HTTP: no live calls in pytest.

Calls are minimal pairs written for these tests, not taken from any scenario file.
Fake answers stand in for Jev; they check the decision table and the plumbing, not accuracy.
"""
import json
import logging
from pathlib import Path

import httpx
import pytest

from app import intent
from app.models import Scenario, Segment
from app.rules import decide, detect

V = "v1.0"
NO = dict.fromkeys(intent.QUESTIONS, 0.02)
DEMO = Path(__file__).resolve().parents[2] / "scenarios" / "demo"


def call(*turns):
    """turns: plain strings are the caller; ("subscriber", text) tuples are the subscriber."""
    return [Segment(seq=i, speaker=t[0] if isinstance(t, tuple) else "caller",
                    text=t[1] if isinstance(t, tuple) else t, source="script")
            for i, t in enumerate(turns, 1)]


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("INTENT_MODEL", "on")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    intent.clear_cache()
    yield
    intent.clear_cache()


@pytest.fixture
def jev(on, monkeypatch):
    """Fake httpx.post: answers from `script(caller_turn) -> {question: noul}`; records requests."""
    sent = []

    def install(script):
        def post(url, json, timeout, headers):
            sent.append(dict(url=url, json=json, timeout=timeout, headers=headers))
            nouls = {**NO, **script(json["state"]["caller_turn"])}
            body = {"model": json["model"], "usage": {"input_tokens": 1, "output_tokens": 1},
                    "answers": {q: {"type": "noul", "noul": nouls[q]} for q in json["questions"]}}
            return httpx.Response(200, json=body, request=httpx.Request("POST", url))
        monkeypatch.setattr(httpx, "post", post)
        return sent
    return install


def rules_of(segs, arm="C"):
    return [e.rule_id for e in detect(segs, arm, V)]


# --- switch and failure handling ---------------------------------------------

def test_off_without_flag_or_key(monkeypatch):
    monkeypatch.delenv("INTENT_MODEL", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    assert not intent.enabled()
    monkeypatch.setenv("INTENT_MODEL", "on")
    monkeypatch.delenv("TYPESAFE_API_KEY")
    assert not intent.enabled()
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("no call when off"))
    segs = call("Grandma, the lawyer says it's a lot.")
    assert intent.answers(segs) is None
    assert decide(segs, "C", V) == decide(segs, "B", V)


@pytest.mark.parametrize("failure", [
    httpx.ConnectTimeout("timed out"),
    httpx.HTTPStatusError("429", request=httpx.Request("POST", intent.URL), response=httpx.Response(429)),
    KeyError("answers"),
])
def test_failed_call_is_an_error_and_falls_back_to_b(on, monkeypatch, caplog, failure):
    def post(*a, **k):
        raise failure
    monkeypatch.setattr(httpx, "post", post)
    segs = call("Hi, it's the bank.", "I just sent a code. Read it to me.")
    with caplog.at_level(logging.ERROR, logger="app.intent"):
        assert intent.answers(segs) is None
        assert decide(segs, "C", V) == decide(segs, "B", V)
    assert any("falls back to arm B" in r.message for r in caplog.records)


def test_request_shape_auth_timeout_and_cache(jev):
    sent = jev(lambda turn: {})
    segs = call("Hello.", ("subscriber", "Hi, who is this?"), "It's your nephew.", ("subscriber", "Oh!"),
                "I'm in a bit of trouble.")
    intent.answers(segs)
    intent.answers(segs)  # cached: one request
    (req,) = sent
    assert req["url"] == "https://api.typesafe.ai/v1/systemone"
    assert req["headers"] == {"Authorization": "Bearer test-key"}
    assert req["timeout"] == intent.TIMEOUT_S <= 1.5
    body = req["json"]
    assert body["model"].startswith("jev-")
    assert body["state"] == {
        "earlier_turns": [{"speaker": "listener", "text": "Hi, who is this?"},
                          {"speaker": "caller", "text": "It's your nephew."},
                          {"speaker": "listener", "text": "Oh!"}],
        "caller_turn": "I'm in a bit of trouble."}
    assert set(body["questions"]) == {"otp", "payment", "remote", "warning", "reported", "self_service"}
    assert all(q["type"] == "noul" and "`caller_turn`" in q["instructions"] for q in body["questions"].values())


def test_payload_logged_only_in_debug_and_never_the_key(jev, caplog):
    jev(lambda turn: {})
    with caplog.at_level(logging.INFO, logger="app.intent"):
        intent.answers(call("First."))
    assert not caplog.records
    with caplog.at_level(logging.DEBUG, logger="app.intent"):
        intent.answers(call("Second."))
    (rec,) = caplog.records
    assert "Second." in rec.getMessage() and "test-key" not in rec.getMessage()


# --- decision table -----------------------------------------------------------

@pytest.mark.parametrize("category, nouls, lexicon_seen, expected", [
    ("otp", {"otp": 0.95}, False, "solo"),
    ("otp", {"otp": 0.95}, True, "confirm"),
    ("otp", {"otp": 0.8}, True, None),  # not confident enough, lexicon or not
    ("otp", {"otp": 0.95, "warning": 0.6}, True, None),  # a raised guard blocks it
    ("otp", {"otp": 0.95, "reported": 0.6}, False, None),
    ("payment", {"payment": 0.95, "self_service": 0.9}, False, "solo"),  # "buy the cards yourself" is a scam
    ("remote", {"remote": 0.95, "self_service": 0.9}, True, None),  # "update it yourself" is not
    ("remote", {"remote": 0.95, "otp": 0.99}, False, "solo"),  # categories are judged separately
])
def test_judge(category, nouls, lexicon_seen, expected):
    assert intent.judge({**NO, **nouls}, category, lexicon_seen) == expected


# --- arm C through app.rules ----------------------------------------------------

def test_solo_detection_has_its_own_rule_id(jev):
    jev(lambda turn: {"payment": 0.97} if "help me out" in turn else {})
    segs = call("Grandpa, it's me. I'm in trouble and I didn't know who else to call.",
                ("subscriber", "Oh no."), "Can you help me out, quick?")
    assert decide(segs, "B", V) == []
    (d,) = decide(segs, "C", V)
    assert (d.template_id, d.basis) == ("ALERT-PAY-01", ["C-INTENT-PAY-SOLO"])
    (e,) = detect(segs, "C", V)
    assert (e.source, e.confidence_class, e.span_seq) == ("intent", "low", [3])


def test_confirmation_needs_the_lexicon(jev):
    # "code" is in the window, the request isn't one B can parse, Jev is sure.
    jev(lambda turn: {"otp": 0.95} if "need that" in turn else {})
    segs = call("The system will text you a code.", "I'm going to need that from you to verify.")
    assert decide(segs, "B", V) == []
    assert rules_of(segs) == ["C-INTENT-OTP-01"]
    # The same answer with no lexicon support anywhere is a model-only detection.
    assert rules_of(call("I'm going to need that from you to verify.")) == ["C-INTENT-OTP-SOLO"]


def test_guards_block_model_detections(jev):
    jev(lambda turn: {"otp": 0.97, "warning": 0.95})
    assert rules_of(call("We'd never want that from you, remember.")) == []


def test_b_rules_are_never_vetoed_and_fired_categories_not_asked(jev):
    sent = jev(lambda turn: {"otp": 0.01})
    assert rules_of(call("Read me the code now.")) == ["B-OTP-REQ-01"]
    assert len(sent) == 1  # still asked once, for the other categories
    sent.clear()
    assert rules_of(call("Read me the code, then send the gift cards, then install AnyDesk.")) == [
        "B-OTP-REQ-01", "B-PAY-REQ-01", "B-REMOTE-REQ-01"]
    assert sent == []  # every category already fired: no call


def test_only_caller_turns_are_sent(jev):
    sent = jev(lambda turn: {})
    detect(call(("subscriber", "Read me the code."), "Okay."), "C", V)
    assert [r["json"]["state"]["caller_turn"] for r in sent] == ["Okay."]


@pytest.mark.parametrize("scenario_id, expected", [("clinic", []), ("bank", ["ALERT-OTP-01"])])
def test_demo_replays_with_the_model_on(jev, scenario_id, expected):
    jev(lambda turn: {})
    sc = Scenario.model_validate(json.loads((DEMO / f"{scenario_id}.json").read_text()))
    segs = call(*[t.text if t.speaker == "caller" else ("subscriber", t.text) for t in sc.turns])
    assert [d.template_id for d in decide(segs, "C", V)] == expected
