"""SMS gateway (issues #17, #68): keywords, message-id dedupe, signatures, consent refusal, privacy.

The Photon API is always mocked; nothing leaves the machine.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import consent, sms, storage
from app.main import create_app
from app.policy import templates

DEMO = "+15551234567"
SECRET = "whsec_" + base64.b64encode(b"photon-signing-key").decode()
SENDER = "pho_usr_sender"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "safesignal.db")
    for k, v in {"CONSENT_SALT": "salt", "DEMO_PHONE": DEMO, "PHOTON_API_KEY": "pho_sk_test",
                 "PHOTON_PROJECT_ID": "pho_prj_test", "PHOTON_SENDER_ID": SENDER,
                 "PHOTON_WEBHOOK_SECRET": SECRET, "OPERATOR_PASSWORD": "op", "SESSION_SECRET": "secret"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sms, "_mode", "simulated")
    monkeypatch.setattr(sms, "_last_alert", None)
    monkeypatch.setattr(sms, "_sent", {})
    monkeypatch.setattr(sms, "_seen_sids", set())
    monkeypatch.setattr(sms, "_simulated", sms.SimulatedGateway())
    monkeypatch.setattr(sms, "_photon", None)


@pytest.fixture
def events(monkeypatch):
    seen = []
    monkeypatch.setattr(sms, "emit", lambda type, payload, ref: seen.append((type, payload, ref)))
    monkeypatch.setattr(consent, "emit", lambda type, payload, ref: seen.append((type, payload, ref)))
    return seen


@pytest.fixture
def photon(monkeypatch):
    """Fake Photon API; returns the list of (path, idempotency-key, json body) it received."""
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append((request.url.path, request.headers.get("idempotency-key"), body))
        prefix = {"users": "pho_usr_", "spaces": "pho_spc_", "messages": "pho_msg_"}[request.url.path.rsplit("/", 1)[1]]
        return httpx.Response(201, json={"id": f"{prefix}{len(calls)}"})

    gateway = sms.PhotonGateway()
    gateway.http = httpx.Client(base_url=gateway.http.base_url, headers=gateway.http.headers,
                                transport=httpx.MockTransport(handler))
    monkeypatch.setattr(sms, "_photon", gateway)
    return calls


def sent_texts(calls):
    return [body["content"]["text"] for path, _, body in calls if path.endswith("/messages")]


def alerted(ref="sess1", template_id="ALERT-OTP-01"):
    consent.set_state("active")
    return sms.get_gateway().send(template_id, ref)


def inbound(body, sid="SM1", phone=None):
    return asyncio.run(sms.handle_inbound(sid, body, phone))


def replies():
    return [m["template_id"] for m in sms._simulated.outbox if not m["template_id"].startswith("ALERT-")]


# --- keywords -----------------------------------------------------------------

@pytest.mark.parametrize("body,keyword,template_id", [
    *[(w, "STOP", "R-STOP") for w in
      ["STOP", "stop", "Stop!", "STOPALL", "unsubscribe", "Cancel", "END", "quit", "stop please", "Please stop."]],
    ("START", "START", "R-YES"),
    ("yes", "YES", "R-YES"),
    (" Yes! ", "YES", "R-YES"),
    ("SHARED", "SHARED", "R-SHARED-OTP"),
    ("shared.", "SHARED", "R-SHARED-OTP"),
    ("WRONG", "WRONG", "R-WRONG"),
    ("Wrong.", "WRONG", "R-WRONG"),
    ("HELP", "HELP", "R-HELP"),
    ("what is this?", "HELP", "R-HELP"),
    ("", "HELP", "R-HELP"),
])
def test_every_keyword(events, body, keyword, template_id):
    alerted()
    payload = inbound(body)
    assert payload.keyword == keyword and payload.counted
    assert replies() == [template_id]
    assert ("reply", payload, "sess1") in events


def test_stop_and_start_change_consent(events):
    alerted()
    inbound("STOP", "SM1")
    assert consent.get_state() == "stopped"
    inbound("START", "SM2")
    assert consent.get_state() == "active"
    assert [p.state for t, p, _ in events if t == "consent"] == ["active", "stopped", "active"]


def test_shared_reply_is_category_specific(events):
    alerted(template_id="ALERT-PAY-01")
    inbound("SHARED")
    assert replies() == [templates.shared_for("ALERT-PAY-01")] == ["R-SHARED-PAY"]


def test_reply_without_alert_is_not_counted(events):
    consent.set_state("active")
    shared = inbound("SHARED", "SM1")
    wrong = inbound("WRONG", "SM2")
    assert (shared.keyword, shared.counted) == ("HELP", False)
    assert (wrong.counted, wrong.wrong_count) == (False, 0)
    assert replies() == ["R-HELP", "R-WRONG"]


def test_wrong_counter_runs_across_sessions(events):
    alerted("s1")
    assert inbound("WRONG", "SM1").wrong_count == 1
    alerted("s2")
    second = inbound("wrong", "SM2")
    assert second.wrong_count == 2
    assert ("reply", second, "s2") in events  # attaches to the latest alerted session


def test_stop_in_real_mode_confirms_with_r_stop(events, photon):
    sms.set_mode("real")
    alerted()
    inbound("STOP", "SM1", DEMO)
    assert sent_texts(photon) == [templates.get("ALERT-OTP-01"), templates.get("R-STOP")]
    assert consent.get_state() == "stopped"


# --- dedupe --------------------------------------------------------------------

def test_duplicate_message_sid_ignored(events):
    alerted()
    assert inbound("WRONG", "SMdup") is not None
    assert inbound("WRONG", "SMdup") is None
    assert replies() == ["R-WRONG"]
    assert storage.aggregates()["replies"] == [{"keyword": "WRONG", "template_id": "ALERT-OTP-01", "count": 1}]


# --- consent refusal -----------------------------------------------------------

@pytest.mark.parametrize("mode", ["simulated", "real"])
def test_send_refuses_without_consent(events, photon, mode):
    sms.set_mode(mode)
    for state in [None, "invited", "stopped"]:
        if state:
            consent.set_state(state)
        with pytest.raises(RuntimeError):
            sms.get_gateway().send("ALERT-OTP-01", "sess1")
    assert sms._simulated.outbox == [] and photon == []
    assert sms._last_alert is None


def test_photon_send_creates_space_once_then_sends_template_text(events, photon):
    sms.set_mode("real")
    consent.set_state("active")
    message_id = sms.get_gateway().send("ALERT-OTP-01", "sess1")
    sms.get_gateway().send("ALERT-PAY-01", "sess2")
    base = "/v1/projects/pho_prj_test"
    assert [(path, body) for path, _, body in photon[:2]] == [
        (f"{base}/users", {"handle": DEMO, "platform": "imessage"}),
        (f"{base}/spaces", {"participantIds": [SENDER, "pho_usr_1"], "platform": "imessage"})]
    path, key, body = photon[2]
    assert path == f"{base}/messages" and key
    assert body == {"spaceId": "pho_spc_2", "senderId": SENDER,
                    "content": {"type": "text", "format": "plain", "text": templates.get("ALERT-OTP-01")}}
    assert [p for p, _, _ in photon[3:]] == [f"{base}/messages"]  # space is cached per phone
    assert photon[3][1] != key  # fresh idempotency key per message
    assert sms._sent[message_id] == ("ALERT-OTP-01", "sess1")


def test_unknown_template_raises_before_sending(events):
    consent.set_state("active")
    with pytest.raises(KeyError):
        sms.get_gateway().send("NOPE", "sess1")
    assert sms._simulated.outbox == []


def test_mode_toggle():
    assert sms.get_mode() == "simulated" and isinstance(sms.get_gateway(), sms.SimulatedGateway)
    sms.set_mode("real")
    assert isinstance(sms.get_gateway(), sms.PhotonGateway)


# --- webhooks + signatures -----------------------------------------------------

def event(type, message_id, text=None):
    obj = {"id": message_id, "platform": "imessage", "sentBy": {"handle": DEMO, "id": "pho_usr_peer"}}
    if text is not None:
        obj["content"] = {"type": "text", "format": "plain", "text": text}
    return json.dumps({"id": "evt_1", "type": type, "apiVersion": "2026-07-01", "data": {"object": obj}})


def signed(raw, secret=SECRET, ts=None):
    ts = str(int(time.time()) if ts is None else ts)
    key = base64.b64decode(secret.removeprefix("whsec_"))
    sig = base64.b64encode(hmac.new(key, f"evt_1.{ts}.{raw}".encode(), hashlib.sha256).digest()).decode()
    return {"webhook-id": "evt_1", "webhook-timestamp": ts, "webhook-signature": f"v1,{sig}",
            "content-type": "application/json"}


def post(client, raw, headers):
    return client.post("/sms/inbound", content=raw, headers=headers)


@pytest.fixture
def client():
    return TestClient(create_app())


def test_inbound_webhook_rejects_bad_signature(client, events, monkeypatch):
    raw = event("message.received", "pho_msg_in1", "WRONG")
    other = "whsec_" + base64.b64encode(b"other").decode()
    assert post(client, raw, {"content-type": "application/json"}).status_code == 403
    assert post(client, raw, signed(raw, secret=other)).status_code == 403
    assert post(client, raw, signed(raw, ts=int(time.time()) - 600)).status_code == 403  # stale
    assert post(client, raw + " ", signed(raw)).status_code == 403  # body changed after signing
    monkeypatch.delenv("PHOTON_WEBHOOK_SECRET")
    assert post(client, raw, signed(raw)).status_code == 403  # fails closed without a secret
    assert [e for e in events if e[0] == "reply"] == []


def test_inbound_webhook_accepts_valid_signature(client, events):
    alerted()
    raw = event("message.received", "pho_msg_in9", "Wrong.")
    assert post(client, raw, signed(raw)).status_code == 204
    assert post(client, raw, signed(raw)).status_code == 204  # Photon retry: same message id, ignored
    assert [p.keyword for t, p, _ in events if t == "reply"] == ["WRONG"]


def test_status_webhook_emits_mapped_status(client, events):
    message_id = alerted()
    for event_type in ["message.dispatched", "message.delivered", "message.failed", "message.accepted"]:
        raw = event(event_type, message_id)
        assert post(client, raw, signed(raw)).status_code == 204
    raw = event("message.delivered", "pho_msg_unknown")
    post(client, raw, signed(raw))
    assert [(p.message_id, p.status) for t, p, _ in events if t == "sms"] == [
        (message_id, "sent"), (message_id, "delivered"), (message_id, "failed")]


# --- operator routes -----------------------------------------------------------

def test_operator_routes_need_login(client):
    assert client.post("/sms/simulate-inbound", json={"body": "YES"}).status_code == 401
    assert client.get("/sms/templates/R-HELP").status_code == 401
    assert client.get("/sms/outbox").status_code == 401
    assert client.post("/sms/invite", json={}).status_code == 401


def test_operator_routes(client, events):
    client.post("/login", json={"password": "op"})
    assert client.get("/sms/templates/R-HELP").json() == {"template_id": "R-HELP", "text": templates.get("R-HELP")}
    assert client.get("/sms/templates/NOPE").status_code == 404
    assert client.post("/sms/invite", json={"phone": "demo"}).status_code == 200
    assert consent.get_state() == "invited"
    assert client.post("/sms/invite", json={"phone": "spare"}).status_code == 400  # SPARE_PHONE unset
    assert client.post("/sms/simulate-inbound", json={"body": "yes"}).json()["keyword"] == "YES"
    assert consent.get_state() == "active"
    assert [m["template_id"] for m in client.get("/sms/outbox").json()] == ["ENROLL", "R-YES"]


# --- privacy (SM-06) -----------------------------------------------------------

def test_no_raw_number_or_body_in_logs(client, events, caplog, photon):
    caplog.set_level(logging.DEBUG)
    sms.set_mode("real")
    asyncio.run(sms.invite(DEMO))
    inbound("YES", "SM1", DEMO)
    alerted()
    raw = event("message.received", "pho_msg_in2", "Wrong. my code is 4821")
    post(client, raw, signed(raw))
    assert sent_texts(photon)  # messages went through the mocked API
    for secret in [DEMO, DEMO.lstrip("+"), "4821", templates.get("ALERT-OTP-01"), templates.get("ENROLL")]:
        assert secret not in caplog.text
