"""SMS gateway (issue #17): keywords, MessageSid dedupe, signatures, consent refusal, privacy.

Twilio is always mocked; nothing leaves the machine.
"""
import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app import consent, sms, storage
from app.main import create_app
from app.policy import templates

DEMO = "+15551234567"
TOKEN = "twilio-token"
BASE = "https://safesignal.example.com"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "safesignal.db")
    for k, v in {"CONSENT_SALT": "salt", "DEMO_PHONE": DEMO, "TWILIO_ACCOUNT_SID": "AC123",
                 "TWILIO_AUTH_TOKEN": TOKEN, "TWILIO_FROM": "+15550000000", "PUBLIC_BASE_URL": BASE,
                 "OPERATOR_PASSWORD": "op", "SESSION_SECRET": "secret"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sms, "_mode", "simulated")
    monkeypatch.setattr(sms, "_last_alert", None)
    monkeypatch.setattr(sms, "_sent", {})
    monkeypatch.setattr(sms, "_seen_sids", set())
    monkeypatch.setattr(sms, "_simulated", sms.SimulatedGateway())
    monkeypatch.setattr(sms, "_twilio", None)


@pytest.fixture
def events(monkeypatch):
    seen = []
    monkeypatch.setattr(sms, "emit", lambda type, payload, ref: seen.append((type, payload, ref)))
    monkeypatch.setattr(consent, "emit", lambda type, payload, ref: seen.append((type, payload, ref)))
    return seen


@pytest.fixture
def twilio(monkeypatch):
    created = []

    class FakeClient:
        def __init__(self, sid, token):
            self.messages = self

        def create(self, **kw):
            created.append(kw)
            return SimpleNamespace(sid=f"SM{len(created):032d}")

    monkeypatch.setattr(sms, "Client", FakeClient)
    return created


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


def test_stop_in_real_mode_sends_no_reply(events, twilio):
    sms.set_mode("real")
    alerted()
    inbound("STOP", "SM1", DEMO)
    assert [m["body"] for m in twilio] == [templates.get("ALERT-OTP-01")]


# --- dedupe --------------------------------------------------------------------

def test_duplicate_message_sid_ignored(events):
    alerted()
    assert inbound("WRONG", "SMdup") is not None
    assert inbound("WRONG", "SMdup") is None
    assert replies() == ["R-WRONG"]
    assert storage.aggregates()["replies"] == [{"keyword": "WRONG", "template_id": "ALERT-OTP-01", "count": 1}]


# --- consent refusal -----------------------------------------------------------

@pytest.mark.parametrize("mode", ["simulated", "real"])
def test_send_refuses_without_consent(events, twilio, mode):
    sms.set_mode(mode)
    for state in [None, "invited", "stopped"]:
        if state:
            consent.set_state(state)
        with pytest.raises(RuntimeError):
            sms.get_gateway().send("ALERT-OTP-01", "sess1")
    assert sms._simulated.outbox == [] and twilio == []
    assert sms._last_alert is None


def test_twilio_send_uses_template_text_and_status_callback(events, twilio):
    sms.set_mode("real")
    consent.set_state("active")
    message_id = sms.get_gateway().send("ALERT-OTP-01", "sess1")
    assert twilio == [{"to": DEMO, "from_": "+15550000000", "body": templates.get("ALERT-OTP-01"),
                       "status_callback": f"{BASE}/sms/status"}]
    assert sms._sent[message_id] == ("ALERT-OTP-01", "sess1")


def test_unknown_template_raises_before_sending(events):
    consent.set_state("active")
    with pytest.raises(KeyError):
        sms.get_gateway().send("NOPE", "sess1")
    assert sms._simulated.outbox == []


def test_mode_toggle():
    assert sms.get_mode() == "simulated" and isinstance(sms.get_gateway(), sms.SimulatedGateway)
    sms.set_mode("real")
    assert isinstance(sms.get_gateway(), sms.TwilioGateway)


# --- webhooks + signatures -----------------------------------------------------

def signed(path, params, token=TOKEN):
    return {"X-Twilio-Signature": RequestValidator(token).compute_signature(BASE + path, params)}


@pytest.fixture
def client():
    return TestClient(create_app())


def test_inbound_webhook_rejects_bad_signature(client, events):
    params = {"MessageSid": "SM1", "Body": "WRONG", "From": DEMO}
    assert client.post("/sms/inbound", data=params).status_code == 403
    assert client.post("/sms/inbound", data=params, headers=signed("/sms/inbound", params, "wrong")).status_code == 403
    assert client.post("/sms/status", data=params).status_code == 403
    assert [e for e in events if e[0] == "reply"] == []


def test_inbound_webhook_accepts_valid_signature(client, events):
    alerted()
    params = {"MessageSid": "SM9", "Body": "Wrong.", "From": DEMO}
    r = client.post("/sms/inbound", data=params, headers=signed("/sms/inbound", params))
    assert r.status_code == 200 and "<Response>" in r.text
    assert [p.keyword for t, p, _ in events if t == "reply"] == ["WRONG"]


def test_status_webhook_emits_mapped_status(client, events):
    message_id = alerted()
    for twilio_status, expected in [("sent", "sent"), ("delivered", "delivered"), ("undelivered", "failed")]:
        params = {"MessageSid": message_id, "MessageStatus": twilio_status}
        assert client.post("/sms/status", data=params, headers=signed("/sms/status", params)).status_code == 204
    params = {"MessageSid": "SMunknown", "MessageStatus": "delivered"}
    client.post("/sms/status", data=params, headers=signed("/sms/status", params))
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

def test_no_raw_number_or_body_in_logs(client, events, caplog, twilio):
    caplog.set_level(logging.DEBUG)
    sms.set_mode("real")
    asyncio.run(sms.invite(DEMO))
    inbound("YES", "SM1", DEMO)
    alerted()
    params = {"MessageSid": "SM2", "Body": "Wrong. my code is 4821", "From": DEMO}
    client.post("/sms/inbound", data=params, headers=signed("/sms/inbound", params))
    assert twilio  # messages went through the mocked client
    for secret in [DEMO, DEMO.lstrip("+"), "4821", templates.get("ALERT-OTP-01"), templates.get("ENROLL")]:
        assert secret not in caplog.text
