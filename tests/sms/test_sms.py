"""SMS gateway (issues #17, #78): keywords, MessageSid dedupe, signatures, consent refusal, privacy.

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
BASE = "https://callsafe.example.com"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for k, v in {"CONSENT_SALT": "salt", "DEMO_PHONE": DEMO, "TWILIO_ACCOUNT_SID": "AC123",
                 "TWILIO_AUTH_TOKEN": TOKEN, "TWILIO_FROM": "+15550000000", "PUBLIC_BASE_URL": BASE,
                 "OPERATOR_PASSWORD": "op", "SESSION_SECRET": "secret"}.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def twilio(monkeypatch):
    """Fake Twilio client; returns the list of messages.create kwargs it received."""
    created = []

    class FakeClient:
        def __init__(self, sid, token):
            self.messages = self

        def create(self, **kw):
            created.append(kw)
            return SimpleNamespace(sid=f"SM{len(created):032d}")

    monkeypatch.setattr(sms, "Client", FakeClient)
    return created


def sent_texts(created):
    return [m["body"] for m in created]


def alerted(ref="sess1", template_id="ALERT-OTP-01"):
    consent.set_state("active")
    return sms.get_gateway().send(template_id, ref)


def inbound(body, sid="SM1", phone=None):
    return asyncio.run(sms.handle_inbound(sid, body, phone))


def replies():
    return [m["template_id"] for m in sms.simulated.outbox if not m["template_id"].startswith("ALERT-")]


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
def test_every_keyword(published, body, keyword, template_id):
    alerted()
    payload = inbound(body)
    assert payload.keyword == keyword and payload.counted
    assert replies() == [template_id]
    assert ("reply", payload, "sess1") in published


def test_stop_and_start_change_consent(published):
    alerted()
    inbound("STOP", "SM1")
    assert consent.get_state() == "stopped"
    inbound("START", "SM2")
    assert consent.get_state() == "active"
    assert [p.state for t, p, _ in published if t == "consent"] == ["active", "stopped", "active"]


def test_shared_reply_is_category_specific(published):
    alerted(template_id="ALERT-PAY-01")
    inbound("SHARED")
    assert replies() == [templates.shared_for("ALERT-PAY-01")] == ["R-SHARED-PAY"]


def test_reply_without_alert_is_not_counted(published):
    consent.set_state("active")
    shared = inbound("SHARED", "SM1")
    wrong = inbound("WRONG", "SM2")
    assert (shared.keyword, shared.counted) == ("HELP", False)
    assert (wrong.counted, wrong.wrong_count) == (False, 0)
    assert replies() == ["R-HELP", "R-WRONG"]


def test_wrong_counter_runs_across_sessions(published):
    alerted("s1")
    assert inbound("WRONG", "SM1").wrong_count == 1
    alerted("s2")
    second = inbound("wrong", "SM2")
    assert second.wrong_count == 2
    assert ("reply", second, "s2") in published  # attaches to the latest alerted session


def test_stop_in_real_mode_sends_no_reply(published, twilio):
    sms.set_mode("real")
    alerted()
    inbound("STOP", "SM1", DEMO)
    assert sent_texts(twilio) == [templates.get("ALERT-OTP-01")]  # Twilio confirms STOP itself
    assert consent.get_state() == "stopped"


# --- dedupe --------------------------------------------------------------------

def test_duplicate_message_sid_ignored(published):
    alerted()
    assert inbound("WRONG", "SMdup") is not None
    assert inbound("WRONG", "SMdup") is None
    assert replies() == ["R-WRONG"]
    assert storage.aggregates()["replies"] == [{"keyword": "WRONG", "template_id": "ALERT-OTP-01", "count": 1}]
    assert storage.inbound_seen("SMdup")  # in SQLite: a restart doesn't accept the same text again


def test_failed_stop_is_processed_when_retried(published, monkeypatch):
    consent.set_state("active")
    real_set_state = consent.set_state

    def locked(state, phone=None):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(consent, "set_state", locked)
    with pytest.raises(RuntimeError):
        inbound("STOP", "SMretry")
    assert consent.get_state() == "active" and not storage.inbound_seen("SMretry")
    monkeypatch.setattr(consent, "set_state", real_set_state)
    assert inbound("STOP", "SMretry").keyword == "STOP"  # Twilio's retry is not swallowed as a duplicate
    assert consent.get_state() == "stopped"


# --- reply attribution ---------------------------------------------------------

def test_reply_after_failed_alert_is_not_counted(published, monkeypatch):
    sms.set_mode("real")
    consent.set_state("active")
    class DownClient:
        def __init__(self, sid, token):
            self.messages = self

        def create(self, **kw):
            raise RuntimeError("twilio 503")
    monkeypatch.setattr(sms, "Client", DownClient)
    with pytest.raises(RuntimeError):
        sms.get_gateway().send("ALERT-OTP-01", "sess1")
    sms.set_mode("simulated")
    assert inbound("WRONG", "SM1").counted is False
    assert storage.aggregates()["replies"] == []


def test_reply_from_unalerted_spare_phone_is_not_counted(published, monkeypatch):
    spare = DEMO[:-1] + "9"
    monkeypatch.setenv("SPARE_PHONE", spare)
    alerted()  # alerts go to DEMO_PHONE
    assert inbound("WRONG", "SM1", spare).counted is False
    assert inbound("WRONG", "SM2", DEMO).counted is True


# --- consent refusal -----------------------------------------------------------

@pytest.mark.parametrize("mode", ["simulated", "real"])
def test_send_refuses_without_consent(published, twilio, mode):
    sms.set_mode(mode)
    for state in [None, "invited", "stopped"]:
        if state:
            consent.set_state(state)
        with pytest.raises(RuntimeError):
            sms.get_gateway().send("ALERT-OTP-01", "sess1")
    assert sms.simulated.outbox == [] and twilio == []


def test_twilio_send_uses_template_text_and_status_callback(published, twilio):
    sms.set_mode("real")
    consent.set_state("active")
    sms.get_gateway().send("ALERT-OTP-01", "sess1")
    assert twilio == [{"to": DEMO, "from_": "+15550000000", "body": templates.get("ALERT-OTP-01"),
                       "status_callback": f"{BASE}/sms/status"}]


def test_unknown_template_raises_before_sending(published):
    consent.set_state("active")
    with pytest.raises(KeyError):
        sms.get_gateway().send("NOPE", "sess1")
    assert sms.simulated.outbox == []


def test_mode_toggle():
    assert sms.get_mode() == "simulated" and isinstance(sms.get_gateway(), sms.SimulatedGateway)
    sms.set_mode("real")
    assert isinstance(sms.get_gateway(), sms.TwilioGateway)


# --- webhooks + signatures -----------------------------------------------------

def signed(path, params, token=TOKEN):
    return {"X-Twilio-Signature": RequestValidator(token).compute_signature(BASE + path, params)}


def post(client, body, sid="SMin1", sender=DEMO, path="/sms/inbound"):
    params = {"MessageSid": sid, "Body": body, "From": sender}
    return client.post(path, data=params, headers=signed(path, params))


@pytest.fixture
def client():
    return TestClient(create_app())


def test_inbound_webhook_rejects_bad_signature(client, published, monkeypatch):
    params = {"MessageSid": "SM1", "Body": "WRONG", "From": DEMO}
    assert client.post("/sms/inbound", data=params).status_code == 403
    assert client.post("/sms/inbound", data=params, headers=signed("/sms/inbound", params, "wrong")).status_code == 403
    assert client.post("/sms/status", data=params).status_code == 403
    assert [e for e in published if e[0] == "reply"] == []


@pytest.mark.parametrize("unset", ["TWILIO_AUTH_TOKEN", "PUBLIC_BASE_URL"])
def test_webhooks_fail_closed_when_unconfigured(client, published, monkeypatch, unset):
    monkeypatch.delenv(unset)
    for path in ["/sms/inbound", "/sms/status"]:
        params = {"MessageSid": "SM1", "Body": "STOP", "From": DEMO, "MessageStatus": "delivered"}
        forged = {"X-Twilio-Signature": RequestValidator("").compute_signature(BASE + path, params)}
        assert client.post(path, data=params, headers=forged).status_code == 403
        assert client.post(path, data=params, headers=signed(path, params)).status_code == 403
    assert published == []


@pytest.mark.parametrize("sender", ["", "+10000000000", "someone@example.com"])
def test_inbound_ignores_missing_or_unenrolled_sender(client, published, twilio, sender):
    sms.set_mode("real")
    consent.set_state("stopped")
    r = post(client, "YES", "SMx", sender)
    assert r.status_code == 200 and "<Response>" in r.text
    assert consent.get_state() == "stopped"  # an unidentified YES never opts the demo phone back in
    assert twilio == [] and [e for e in published if e[0] == "reply"] == []


def test_inbound_replies_only_to_the_configured_number(client, published, twilio):
    sms.set_mode("real")
    consent.set_state("active")
    assert post(client, "HELP", "SMy", DEMO.lstrip("+")).status_code == 200  # same digits, other formatting
    assert [m["to"] for m in twilio] == [DEMO]


def test_inbound_processing_failure_is_5xx_so_twilio_retries(published, monkeypatch):
    def locked(state, phone=None):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(consent, "set_state", locked)
    r = post(TestClient(create_app(), raise_server_exceptions=False), "STOP", "SMz")
    assert r.status_code == 500 and not storage.inbound_seen("SMz")


def test_inbound_webhook_accepts_valid_signature_and_dedupes(client, published):
    alerted()
    r = post(client, "Wrong.", "SM9")
    assert r.status_code == 200 and "<Response>" in r.text
    assert post(client, "Wrong.", "SM9").status_code == 200  # same MessageSid again: ignored
    assert [p.keyword for t, p, _ in published if t == "reply"] == ["WRONG"]


def test_status_webhook_emits_mapped_status(client, published, twilio):
    sms.set_mode("real")
    message_id = alerted()
    for twilio_status, expected in [("sent", "sent"), ("delivered", "delivered"), ("undelivered", "failed")]:
        params = {"MessageSid": message_id, "MessageStatus": twilio_status}
        assert client.post("/sms/status", data=params, headers=signed("/sms/status", params)).status_code == 204
    params = {"MessageSid": "SMunknown", "MessageStatus": "delivered"}
    client.post("/sms/status", data=params, headers=signed("/sms/status", params))
    assert [(p.message_id, p.status) for t, p, _ in published if t == "sms"] == [
        (message_id, "sent"), (message_id, "delivered"), (message_id, "failed")]


def test_tunnel_reaches_only_twilio_webhooks_and_health(client, published):
    via_tunnel = {"Cf-Connecting-Ip": "203.0.113.7"}
    for method, path in [("POST", "/login"), ("GET", "/events/stream"), ("POST", "/demo/reset"),
                         ("GET", "/sms/outbox"), ("POST", "/sms/simulate-inbound"), ("GET", "/state")]:
        assert client.request(method, path, headers=via_tunnel).status_code == 404, path
    assert client.get("/health", headers=via_tunnel).status_code == 200
    params = {"MessageSid": "SMt", "Body": "HELP", "From": DEMO}
    r = client.post("/sms/inbound", data=params, headers={**signed("/sms/inbound", params), **via_tunnel})
    assert r.status_code == 200 and "<Response>" in r.text


# --- operator routes -----------------------------------------------------------

def test_login_opt_in_choice_sets_consent_without_texting(client, published):
    client.post("/login", json={"password": "op"})
    assert client.post("/sms/consent", json={"opt_in": True}).json() == {"consent": "active"}
    assert consent.get_state() == "active"
    assert client.post("/sms/consent", json={"opt_in": False}).json() == {"consent": "stopped"}
    assert consent.get_state() == "stopped"
    assert client.get("/sms/outbox").json() == []  # no R-YES / R-STOP text for the prompt choice
    assert [(t, p.state) for t, p, _ in published] == [("consent", "active"), ("consent", "stopped")]


def test_operator_routes(client, published):
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

def test_no_raw_number_or_body_in_logs(client, published, caplog, twilio):
    caplog.set_level(logging.DEBUG)
    sms.set_mode("real")
    asyncio.run(sms.invite(DEMO))
    inbound("YES", "SM1", DEMO)
    alerted()
    post(client, "Wrong. my code is 4821", "SMin2")
    assert sent_texts(twilio)  # messages went through the mocked client
    for secret in [DEMO, DEMO.lstrip("+"), "4821", templates.get("ALERT-OTP-01"), templates.get("ENROLL")]:
        assert secret not in caplog.text
