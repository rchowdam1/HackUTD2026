"""Live mic conversation (#100): turns in, alert mid-call, follow-up only on End call."""
import pytest
from fastapi.testclient import TestClient

from app import asr, pipeline
from app.main import create_app

ASK = "I just sent a code to your phone. Can you read it back to me?"


@pytest.fixture
def live(monkeypatch, published):
    """Logged-in, opted-in client; the fake transcriber hears the clip's bytes as its text."""
    monkeypatch.setenv("OPERATOR_PASSWORD", "op-pass")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("DEMO_PHONE", "+12145551234")
    monkeypatch.setenv("CONSENT_SALT", "test-salt")
    monkeypatch.setattr(asr, "load_model", lambda: None)
    monkeypatch.setattr(asr, "transcribe", lambda clip, beam_size=5: ([(0.0, 1.0, t)] if (t := clip.read().decode()) else [], 1.0))
    with TestClient(create_app()) as c:  # one event loop for the whole test, so queued sends run
        assert c.post("/login", json={"password": "op-pass"}).status_code == 200
        assert c.post("/sms/consent", json={"opt_in": True}).status_code == 200
        yield c


def say(c, speaker, text):
    return c.post("/live/utterance", data={"speaker": speaker}, files={"audio": ("turn.webm", text.encode(), "audio/webm")})


def test_alert_keeps_the_call_running_and_end_call_sends_the_follow_up(live, published):
    ref = live.post("/live/start").json()["session_ref"]
    assert say(live, "caller", "Hi, this is the fraud team at your bank.").json() == {"text": "Hi, this is the fraud team at your bank."}
    say(live, "caller", ASK)
    say(live, "subscriber", "Um, okay, hold on.")
    segs = [p for t, p, r in published if t == "segment" and r == ref]
    assert [(s.seq, s.speaker, s.source) for s in segs] == [(1, "caller", "asr"), (2, "caller", "asr"), (3, "subscriber", "asr")]
    assert all(s.ended_at for s in segs)  # alert latency is timed from the tap that ended the turn
    assert {p.source for t, p, r in published if t == "session" and r == ref} == {"mic"}
    assert [p.template_id for t, p, _ in published if t == "decision"] == ["ALERT-OTP-01"]
    assert not pipeline.current().finished  # the alert didn't end the call

    assert live.post("/demo/end-call").status_code == 200
    tail = [(t, getattr(p, "template_id", None) or getattr(p, "state", None)) for t, p, _ in published if t in ("sms", "session")]
    assert tail == [("session", "running"), ("sms", "ALERT-OTP-01"), ("sms", "FU-OTP-01"), ("session", "finished")]
    assert say(live, "caller", "Hello?").status_code == 409


def test_silent_turn_adds_no_line(live, published):
    live.post("/live/start")
    assert say(live, "caller", "").json() == {"text": ""}
    assert not [t for t, _, _ in published if t == "segment"]


def test_turn_without_a_conversation_is_refused(live):
    assert say(live, "caller", "Hello?").status_code == 409
