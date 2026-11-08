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
