"""SMS gateway (issues #17, #68): keywords, message-id dedupe, bridge auth, consent refusal, privacy.

The Spectrum bridge is always mocked; nothing leaves the machine.
"""
import asyncio
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app import consent, sms, storage
from app.main import create_app
from app.policy import templates

DEMO = "+15551234567"
TOKEN = "bridge-token"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "safesignal.db")
    for k, v in {"CONSENT_SALT": "salt", "DEMO_PHONE": DEMO, "PHOTON_BRIDGE_TOKEN": TOKEN,
                 "OPERATOR_PASSWORD": "op", "SESSION_SECRET": "secret"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sms, "_mode", "simulated")
    monkeypatch.setattr(sms, "_last_alerts", {})
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
    """Fake Spectrum bridge; returns the list of (path, x-bridge-token, json body) it received."""
    calls = []

    def handler(request):
        calls.append((request.url.path, request.headers.get("x-bridge-token"), json.loads(request.content)))
        return httpx.Response(200, json={"id": f"spc-msg-{len(calls)}"})

    gateway = sms.PhotonGateway()
    gateway.http = httpx.Client(base_url=gateway.http.base_url, headers=gateway.http.headers,
                                transport=httpx.MockTransport(handler))
    monkeypatch.setattr(sms, "_photon", gateway)
    return calls


def sent_texts(calls):
    return [body["text"] for _, _, body in calls]


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
    assert storage.inbound_seen("SMdup")  # in SQLite: a restart doesn't accept the same text again


def test_failed_stop_is_processed_when_retried(events, monkeypatch):
    consent.set_state("active")
    real_set_state = consent.set_state

    def locked(state, phone=None):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(consent, "set_state", locked)
    with pytest.raises(RuntimeError):
        inbound("STOP", "SMretry")
    assert consent.get_state() == "active" and not storage.inbound_seen("SMretry")
    monkeypatch.setattr(consent, "set_state", real_set_state)
    assert inbound("STOP", "SMretry").keyword == "STOP"  # the bridge's retry is not swallowed as a duplicate
    assert consent.get_state() == "stopped"


# --- reply attribution ---------------------------------------------------------

def test_reply_after_failed_alert_is_not_counted(events, monkeypatch):
    sms.set_mode("real")
    consent.set_state("active")
    gateway = sms.PhotonGateway()
    gateway.http = httpx.Client(base_url="http://bridge", transport=httpx.MockTransport(lambda r: httpx.Response(502)))
    monkeypatch.setattr(sms, "_photon", gateway)
    with pytest.raises(httpx.HTTPStatusError):
        sms.get_gateway().send("ALERT-OTP-01", "sess1")
    sms.set_mode("simulated")
    assert inbound("WRONG", "SM1").counted is False
    assert storage.aggregates()["replies"] == []


def test_reply_from_unalerted_spare_phone_is_not_counted(events, monkeypatch):
    spare = DEMO[:-1] + "9"
    monkeypatch.setenv("SPARE_PHONE", spare)
    alerted()  # alerts go to DEMO_PHONE
    assert inbound("WRONG", "SM1", spare).counted is False
    assert inbound("WRONG", "SM2", DEMO).counted is True


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
    assert sms._last_alerts == {}


def test_photon_send_posts_template_text_to_bridge(events, photon):
    sms.set_mode("real")
    consent.set_state("active")
    assert sms.get_gateway().send("ALERT-OTP-01", "sess1") == "spc-msg-1"
    assert photon == [("/send", TOKEN, {"to": DEMO, "text": templates.get("ALERT-OTP-01")})]


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

def post(client, text, message_id="spc-msg-in1", token=TOKEN):
    headers = {"x-bridge-token": token} if token else {}
    return client.post("/sms/inbound", json={"id": message_id, "text": text, "sender": DEMO}, headers=headers)


@pytest.fixture
def client():
    return TestClient(create_app())


def test_inbound_rejects_bad_bridge_token(client, events, monkeypatch):
    assert post(client, "WRONG", token=None).status_code == 403
    assert post(client, "WRONG", token="nope").status_code == 403
    monkeypatch.delenv("PHOTON_BRIDGE_TOKEN")
    assert post(client, "WRONG").status_code == 403  # fails closed without a token
    assert [e for e in events if e[0] == "reply"] == []


@pytest.mark.parametrize("sender", [None, "", "+10000000000", "someone@example.com"])
def test_inbound_ignores_missing_or_unenrolled_sender(client, events, photon, sender):
    sms.set_mode("real")
    consent.set_state("stopped")
    r = client.post("/sms/inbound", json={"id": "spc-in-x", "text": "YES", "sender": sender},
                    headers={"x-bridge-token": TOKEN})
    assert r.status_code == 204
    assert consent.get_state() == "stopped"  # an unidentified YES never opts the demo phone back in
    assert photon == [] and [e for e in events if e[0] == "reply"] == []


def test_inbound_replies_only_to_the_configured_number(client, events, photon):
    sms.set_mode("real")
    consent.set_state("active")
    formatted = DEMO.lstrip("+")  # same digits, different formatting from the bridge
    r = client.post("/sms/inbound", json={"id": "spc-in-y", "text": "HELP", "sender": formatted},
                    headers={"x-bridge-token": TOKEN})
    assert r.status_code == 204
    assert [body["to"] for _, _, body in photon] == [DEMO]


def test_inbound_processing_failure_is_5xx_so_the_bridge_retries(events, monkeypatch):
    def locked(state, phone=None):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(consent, "set_state", locked)
    r = TestClient(create_app(), raise_server_exceptions=False).post(
        "/sms/inbound", json={"id": "spc-in-z", "text": "STOP", "sender": DEMO}, headers={"x-bridge-token": TOKEN})
    assert r.status_code == 500 and not storage.inbound_seen("spc-in-z")


def test_inbound_accepts_bridge_token_and_dedupes(client, events):
    alerted()
    assert post(client, "Wrong.", "spc-msg-in9").status_code == 204
    assert post(client, "Wrong.", "spc-msg-in9").status_code == 204  # same message id again: ignored
    assert [p.keyword for t, p, _ in events if t == "reply"] == ["WRONG"]


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
    post(client, "Wrong. my code is 4821", "spc-msg-in2")
    assert sent_texts(photon)  # messages went through the mocked bridge
    for secret in [DEMO, DEMO.lstrip("+"), "4821", templates.get("ALERT-OTP-01"), templates.get("ENROLL")]:
        assert secret not in caplog.text
