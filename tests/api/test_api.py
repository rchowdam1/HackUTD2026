"""Operator API (issue #19): auth, results file, aggregates, SSE relay, demo controls."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import ingest, pipeline, sms, storage
from app.api import results, stream
from app.events import hub
from app.main import create_app
from app.models import Event

PROTECTED = [
    ("GET", "/events/stream"),
    ("POST", "/demo/run/bank"),
    ("POST", "/demo/end-call"),
    ("POST", "/demo/reset"),
    ("POST", "/demo/sms-mode"),
    ("GET", "/results/latest"),
    ("GET", "/aggregates"),
]


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("OPERATOR_PASSWORD", "op-pass")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "safesignal.db")
    monkeypatch.setattr(results, "RESULTS", tmp_path / "results" / "latest.json")


@pytest.fixture
def client():
    return TestClient(create_app())  # no `with`: skips lifespan (ASR preload)


@pytest.fixture
def operator(client):
    assert client.post("/login", json={"password": "op-pass"}).status_code == 200
    return client


def test_wrong_password_rejected(client):
    r = client.post("/login", json={"password": "nope"})
    assert r.status_code == 401 and "safesignal_session" not in r.cookies


@pytest.mark.parametrize("method,path", PROTECTED)
def test_routes_require_login(client, method, path):
    assert client.request(method, path).status_code == 401


@pytest.mark.parametrize("method,path", PROTECTED)
def test_forged_cookie_rejected(client, method, path):
    client.cookies.set("safesignal_session", "abc.deadbeef")
    assert client.request(method, path).status_code == 401


def test_health_and_login_are_open(client):
    assert client.get("/health").status_code == 200


def test_results_pending_when_missing(operator):
    r = operator.get("/results/latest")
    assert r.status_code == 200 and r.json() == {"status": "pending"}


def test_results_returned_unchanged(operator):
    raw = b'{"batch": "H1", "source": "script", "arms": {}}\n'
    results.RESULTS.parent.mkdir(parents=True)
    results.RESULTS.write_bytes(raw)
    r = operator.get("/results/latest")
    assert r.status_code == 200 and r.content == raw


def test_aggregates(operator):
    storage.incr_reply("WRONG", "FU-OTP-01")
    assert operator.get("/aggregates").json()["replies"] == [
        {"keyword": "WRONG", "template_id": "FU-OTP-01", "count": 1}]


def test_sse_relays_a_fake_event(fixtures_dir):
    event = Event.model_validate_json((fixtures_dir / "events" / "sms.json").read_text())

    async def first_line():
        lines = stream.event_lines()
        nxt = asyncio.create_task(anext(lines))
        while not hub._subscribers:
            await asyncio.sleep(0)
        hub.publish(event)
        line = await asyncio.wait_for(nxt, 1)
        await lines.aclose()
        return line

    line = asyncio.run(first_line())
    assert line.startswith("data: ") and line.endswith("\n\n")
    assert Event.model_validate(json.loads(line[len("data: "):])) == event
    assert not hub._subscribers  # unsubscribed on close


def test_demo_controls(operator, monkeypatch):
    calls = []
    monkeypatch.setattr(sms, "get_mode", lambda: "simulated", raising=False)
    monkeypatch.setattr(sms, "set_mode", lambda m: calls.append(("set_mode", m)), raising=False)

    def fake_run(scenario_id, *, sms_mode):
        calls.append(("run", scenario_id, sms_mode))
        return asyncio.sleep(0)

    async def fake_reset():
        calls.append(("reset",))

    monkeypatch.setattr(ingest, "run", fake_run)
    monkeypatch.setattr(pipeline, "reset", fake_reset)

    assert operator.post("/demo/run/nope").status_code == 404
    assert operator.post("/demo/run/bank").json() == {"scenario_id": "bank", "sms_mode": "simulated"}
    assert operator.post("/demo/end-call").status_code == 200
    assert operator.post("/demo/reset").status_code == 200
    assert operator.post("/demo/sms-mode", json={"mode": "real"}).status_code == 200
    assert operator.post("/demo/sms-mode", json={"mode": "loud"}).status_code == 422
    assert calls == [("run", "bank", "simulated"), ("reset",), ("set_mode", "real")]


# --- sessions: expiry, revocation, Secure, throttling -----------------------------------------

def test_login_cookie_has_max_age_and_no_secure_on_http(client):
    r = client.post("/login", json={"password": "op-pass"})
    cookie = r.headers["set-cookie"].lower()
    assert "max-age=" in cookie and "httponly" in cookie and "samesite=strict" in cookie and "secure" not in cookie


def test_login_cookie_is_secure_behind_https(client):
    r = client.post("/login", json={"password": "op-pass"}, headers={"x-forwarded-proto": "https"})
    assert "secure" in r.headers["set-cookie"].lower()


def test_logout_revokes_the_session(operator):
    stolen = operator.cookies.get("safesignal_session")
    assert operator.post("/logout").status_code == 200
    operator.cookies.set("safesignal_session", stolen)  # a copied cookie stops working too
    assert operator.get("/aggregates").status_code == 401


def test_expired_session_rejected(operator, monkeypatch):
    import time
    from app.api import auth
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + auth.SESSION_TTL_S + 1)
    assert operator.get("/aggregates").status_code == 401


def test_signed_cookie_without_server_session_rejected(client):
    from app.api import auth
    client.cookies.set("safesignal_session", f"abc.{auth._sign('abc')}")
    assert client.get("/aggregates").status_code == 401


def test_login_throttled_after_repeated_failures(client, monkeypatch):
    from app.api import auth
    monkeypatch.setattr(auth, "_failures", {})
    for _ in range(auth.MAX_FAILURES):
        assert client.post("/login", json={"password": "nope"}).status_code == 401
    r = client.post("/login", json={"password": "op-pass"})  # even the right password waits
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_api_docs_off_unless_asked(monkeypatch):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert TestClient(create_app()).get(path).status_code == 404
    monkeypatch.setenv("API_DOCS", "on")
    assert TestClient(create_app()).get("/openapi.json").status_code == 200


# --- GET /state: snapshot for reconnecting consoles ---------------------------------------------

def test_state_requires_login(client):
    assert client.get("/state").status_code == 401


def test_state_replays_events_since_the_latest_session_start(operator, monkeypatch):
    from app.events import emit
    from app.models import SessionPayload, SmsPayload
    monkeypatch.setattr(hub, "history", [])
    monkeypatch.setattr(sms, "_mode", "real")
    emit("sms", SmsPayload(message_id="old", template_id="ALERT-OTP-01", status="queued"), "s0")
    emit("session", SessionPayload(state="running", arm="B", sms_mode="real"), "s1")
    emit("sms", SmsPayload(message_id="", template_id="ALERT-OTP-01", status="failed"), "s1")
    emit("session", SessionPayload(state="finished", arm="B", sms_mode="real"), "s1")
    storage.incr_reply("WRONG", "ALERT-OTP-01")
    body = operator.get("/state").json()
    assert body["sms_mode"] == "real" and body["wrong_count"] == 1
    assert [(e["type"], e["payload"].get("state") or e["payload"].get("status")) for e in body["events"]] == [
        ("session", "running"), ("sms", "failed"), ("session", "finished")]
