"""Live calls (#94): voice webhook TwiML, signature checks, and a synthetic Twilio Media Stream
driven end to end through /voice/stream. Whisper is faked: each utterance pops the next line."""
import base64
import time
import warnings
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from twilio.request_validator import RequestValidator

from app import asr
from app.ingest import live
from app.main import create_app

DEMO = "+15551234567"
TOKEN = "twilio-token"
BASE = "https://callsafe.example.com"
STREAM = "wss://callsafe.example.com/voice/stream"
FRAME = 160  # bytes of mu-law per 20 ms frame
LOUD = bytes([0x00, 0x80] * (FRAME // 2))  # +-32124, full scale
QUIET = bytes([0xFF] * FRAME)  # 0


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for k, v in {"CONSENT_SALT": "salt", "DEMO_PHONE": DEMO, "TWILIO_AUTH_TOKEN": TOKEN,
                 "PUBLIC_BASE_URL": BASE}.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def client():
    return TestClient(create_app())  # no `with`: skips lifespan (ASR preload)


def sign(url: str, params: dict) -> str:
    return RequestValidator(TOKEN).compute_signature(url, params)


def test_incoming_streams_both_tracks_then_dials_demo_phone(client):
    form = {"CallSid": "CA1", "From": "+15550009999"}
    r = client.post("/voice/incoming", data=form, headers={"X-Twilio-Signature": sign(BASE + "/voice/incoming", form)})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/xml")
    start, dial = ET.fromstring(r.text)
    assert (start.tag, start[0].tag, start[0].get("url"), start[0].get("track")) == \
        ("Start", "Stream", STREAM, "both_tracks")
    assert (dial.tag, dial.text) == ("Dial", DEMO)


def test_incoming_unsigned_is_403(client):
    assert client.post("/voice/incoming", data={"CallSid": "CA1"}).status_code == 403


@pytest.mark.parametrize("signature", ["", "forged"])
def test_stream_refuses_unsigned_socket(client, signature):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/voice/stream", headers={"x-twilio-signature": signature}):
            pass


def media(track: str, ms: int, payload: bytes) -> dict:
    return {"event": "media", "media": {"track": track, "timestamp": str(ms),
                                        "payload": base64.b64encode(payload).decode()}}


def call(script: list[tuple[str, int, bool]]) -> list[dict]:
    """Twilio messages for (track, duration_ms, loud) spans; the other track is quiet meanwhile."""
    msgs, t = [{"event": "connected"}, {"event": "start", "start": {"tracks": ["inbound", "outbound"]}}], 0
    for track, duration_ms, loud in script:
        for _ in range(duration_ms // 20):
            other = "outbound" if track == "inbound" else "inbound"
            msgs += [media(track, t, LOUD if loud else QUIET), media(other, t, QUIET)]
            t += 20
    return msgs + [{"event": "stop"}]


def test_stream_transcribes_each_side_and_alerts_on_the_code_request(client, monkeypatch, published):
    lines = iter(["A purchase we want to block. I just sent a verification code to your phone.",
                  "Oh no, what kind of charge?",
                  "Can you read me the code so I can confirm it's you?"])
    heard = []

    def fake_transcribe(wav):
        heard.append(len(wav.getvalue()))
        return [(0.0, 0.5, next(lines))], 0.5

    monkeypatch.setattr(asr, "transcribe", fake_transcribe)
    msgs = call([("inbound", 600, True), ("inbound", 800, False),
                 ("outbound", 100, True), ("outbound", 800, False),  # a click: too short to transcribe
                 ("outbound", 400, True), ("outbound", 800, False),
                 ("inbound", 600, True)])  # still talking at stop: flushed
    with client.websocket_connect("/voice/stream", headers={"x-twilio-signature": sign(STREAM, {})}) as ws:
        for m in msgs:
            ws.send_json(m)
        deadline = time.monotonic() + 5  # leaving the block cancels the handler, so wait for the call to finish
        while not any(t == "session" and p.state == "finished" for t, p, _ in published) and time.monotonic() < deadline:
            time.sleep(0.01)

    segments = [p for t, p, _ in published if t == "segment"]
    assert [(s.speaker, s.source) for s in segments] == \
        [("caller", "asr"), ("subscriber", "asr"), ("caller", "asr")]
    assert [s.seq for s in segments] == [1, 2, 3]
    assert segments[0].t_start_ms == 0 and segments[1].t_start_ms == 2300  # the click at 1400 was dropped
    assert len(heard) == 3
    assert any(t == "decision" and p.level == "action_warning" for t, p, _ in published)
    assert [p.state for t, p, _ in published if t == "session"] == ["running", "finished"]


def test_ulaw_table_matches_g711():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import audioop
    pcm = audioop.ulaw2lin(bytes(range(256)), 2)
    assert [int.from_bytes(pcm[i:i + 2], "little", signed=True) for i in range(0, 512, 2)] == live.ULAW
