"""scripts/preflight check logic with fakes: no network, no Photon bridge, no model."""
import importlib.util
import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import asr, consent

_spec = importlib.util.spec_from_file_location(
    "preflight_checks", Path(__file__).resolve().parents[2] / "scripts" / "preflight_checks.py")
pf = sys.modules["preflight_checks"] = importlib.util.module_from_spec(_spec)  # dataclass needs it registered
_spec.loader.exec_module(pf)

TOKEN = "tok-secret-123"
ENV = {"PHOTON_BRIDGE_TOKEN": TOKEN, "TYPESAFE_API_KEY": "ts-key-456", "DEMO_PHONE": "+12145551234",
       "SPARE_PHONE": "+12145559876", "OPERATOR_PASSWORD": "op-secret-pw"}


class FakeBridge:
    """httpx.get/post stand-ins for the local Spectrum bridge; records POST /send bodies."""

    def __init__(self, status=200, health=True):
        self.status, self.health, self.sent = status, health, []

    def get(self, url):
        if not self.health:
            raise ConnectionError("refused")
        return SimpleNamespace(status_code=200, json=lambda: {"ok": True})

    def post(self, url, json, headers, timeout):
        self.sent.append((url, headers["x-bridge-token"], json))
        return SimpleNamespace(status_code=self.status)


def use_bridge(monkeypatch, fake):
    import httpx
    monkeypatch.setattr(pf, "http_get", fake.get)
    monkeypatch.setattr(httpx, "post", fake.post)
    return fake


# --- masking and env --------------------------------------------------------------------------

def test_scrub_masks_secrets_and_phones():
    text = f"token {TOKEN} key ts-key-456 to {ENV['DEMO_PHONE']}"
    out = pf.scrub(text, ENV)
    assert TOKEN not in out and "ts-key-456" not in out and ENV["DEMO_PHONE"] not in out
    assert "+1******1234" in out


def test_report_scrubs_and_exit_code():
    out = io.StringIO()
    results = [pf.Result("PASS", "a", "ok"), pf.Result("FAIL", "b", f"auth {TOKEN} for +12145551234", "do x")]
    assert pf.report(results, ENV, out) == 1
    text = out.getvalue()
    assert "FAIL b - auth *** for +1******1234\n  fix: do x\n" in text
    assert TOKEN not in text and text.endswith("PREFLIGHT FAIL (1 of 2 checks failed)\n")


def test_report_passes_with_skips():
    out = io.StringIO()
    assert pf.report([pf.Result("PASS", "a", "ok"), pf.Result("SKIP", "sms", "--no-sms")], ENV, out) == 0
    assert "fix:" not in out.getvalue() and "PREFLIGHT PASS" in out.getvalue()


def test_load_env_parses_without_overriding(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("# c\nPF_A=1\nexport PF_B=\"two words\"\nPF_C='x'\nPF_KEEP=new\nnot a line\n")
    monkeypatch.setenv("PF_KEEP", "old")
    for k in ("PF_A", "PF_B", "PF_C"):
        monkeypatch.delenv(k, raising=False)
    pf.load_env(p)
    assert (os.environ["PF_A"], os.environ["PF_B"], os.environ["PF_C"], os.environ["PF_KEEP"]) == \
        ("1", "two words", "x", "old")


def test_main_rejects_unknown_flag():
    assert pf.main(["--bogus"]) == 2


def test_safe_turns_crash_into_fail():
    def boom():
        raise RuntimeError("kaput")
    r = pf._safe("x", boom)
    assert (r.status, r.name) == ("FAIL", "x") and "kaput" in r.detail and r.fix


# --- model / app / replay ----------------------------------------------------------------------

def test_model_fail_names_download(monkeypatch):
    def no_model():
        raise RuntimeError("no cached snapshot")
    monkeypatch.setattr(asr, "load_model", no_model)
    r = pf.check_model()
    assert r.status == "FAIL" and "WhisperModel('small.en'" in r.fix


def test_model_pass_notes_cached_source(monkeypatch):
    monkeypatch.setattr(asr, "load_model", lambda: object())
    monkeypatch.delenv("REPLAY_SOURCE", raising=False)
    r = pf.check_model()
    assert r.status == "PASS" and "cached transcripts" in r.detail


def test_app_missing_routes_fail_names_owner(monkeypatch):
    monkeypatch.delenv("REPLAY_SOURCE", raising=False)
    monkeypatch.setattr(pf, "DEMO_ROUTES", {"/health": "x", "/nope": "b-x #99"})
    r = pf.check_app()
    assert r.status == "FAIL" and "/nope" in r.detail and "b-x #99" in r.fix


def test_app_pass_when_routes_present(monkeypatch):
    monkeypatch.delenv("REPLAY_SOURCE", raising=False)
    monkeypatch.setattr(pf, "DEMO_ROUTES", {"/health": "x"})
    assert pf.check_app().status == "PASS"


def test_app_route_probe_finds_post_route_without_running_it(monkeypatch):
    from fastapi import APIRouter
    from app import main
    router, calls = APIRouter(), []
    router.add_api_route("/demo/run/{scenario_id}", lambda scenario_id: calls.append(scenario_id), methods=["POST"])
    real = main.discover_routers
    monkeypatch.setattr(main, "discover_routers", lambda: real() + [router])
    monkeypatch.setattr(pf, "DEMO_ROUTES", {"/health": "x", "/demo/run/{scenario_id}": "b-api #19"})
    monkeypatch.delenv("REPLAY_SOURCE", raising=False)
    assert pf.check_app().status == "PASS" and calls == []


def test_cached_replay_pass():
    r = pf.check_replay()
    assert r.status == "PASS", r.detail


# --- bridge ------------------------------------------------------------------------------------

def test_bridge_needs_token():
    r = pf.check_bridge({})
    assert r.status == "FAIL" and "PHOTON_BRIDGE_TOKEN" in r.detail


def test_bridge_unreachable(monkeypatch):
    use_bridge(monkeypatch, FakeBridge(health=False))
    r = pf.check_bridge(ENV)
    assert r.status == "FAIL" and "refused" in r.detail and "demo-up" in r.fix


def test_bridge_ok_on_localhost(monkeypatch):
    seen = []
    monkeypatch.setattr(pf, "http_get", lambda url: seen.append(url) or SimpleNamespace(
        status_code=200, json=lambda: {"ok": True}))
    assert pf.check_bridge(ENV).status == "PASS"
    assert seen == ["http://127.0.0.1:8787/health"]


# --- consent / sms -----------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    from app import storage
    monkeypatch.setattr(storage, "init", lambda: None)  # never touch data/safesignal.db from tests


def test_consent_stub_fails_with_owner(monkeypatch):
    monkeypatch.delattr(consent, "get_state", raising=False)
    r = pf.check_consent(ENV)
    assert r.status == "FAIL" and "#18" in r.fix


def test_consent_not_active_masks_phone(monkeypatch):
    states = {ENV["DEMO_PHONE"]: "active", ENV["SPARE_PHONE"]: "stopped"}
    monkeypatch.setattr(consent, "get_state", states.get, raising=False)
    r = pf.check_consent(ENV)
    assert r.status == "FAIL" and "SPARE_PHONE +1******9876 is stopped" in r.detail
    assert ENV["SPARE_PHONE"] not in r.detail


def test_consent_both_active(monkeypatch):
    monkeypatch.setattr(consent, "get_state", lambda phone: "active", raising=False)
    assert pf.check_consent(ENV).status == "PASS"


def test_sms_not_sent_without_consent(monkeypatch):
    fake = use_bridge(monkeypatch, FakeBridge())
    r = pf.check_sms(ENV, consent_ok=False)
    assert r.status == "FAIL" and fake.sent == []


def test_sms_sends_r_help_through_bridge(monkeypatch):
    from app.policy import templates
    fake = use_bridge(monkeypatch, FakeBridge())
    r = pf.check_sms(ENV, consent_ok=True)
    assert r.status == "PASS" and "+1******1234" in r.detail and ENV["DEMO_PHONE"] not in r.detail
    assert fake.sent == [("http://127.0.0.1:8787/send", TOKEN,
                          {"to": ENV["DEMO_PHONE"], "text": templates.get("R-HELP")})]


def test_sms_bridge_refuses(monkeypatch):
    use_bridge(monkeypatch, FakeBridge(status=502))
    r = pf.check_sms(ENV, consent_ok=True)
    assert r.status == "FAIL" and "502" in r.detail and "Photon dashboard" in r.fix


def test_no_sms_flag_skips(monkeypatch):
    for name in ("check_model", "check_app", "check_replay"):
        monkeypatch.setattr(pf, name, lambda n=name: pf.Result("PASS", n, "ok"))
    fake = use_bridge(monkeypatch, FakeBridge())
    results = pf.run_checks({}, send_sms=False)
    assert [(r.name, r.status) for r in results[-2:]] == [("sms", "SKIP"), ("sms-reply", "SKIP")] and fake.sent == []


# --- sms-reply (inbound half of the round trip) --------------------------------------------------

def reply_waiter(got, calls=None):
    """Stand-in for wait_for_reply: records args, 'opens the stream' (calls on_ready), returns `got`."""
    def wait(password, timeout_s, on_ready):
        if calls is not None:
            calls.append((password, timeout_s))
        on_ready()
        if isinstance(got, Exception):
            raise got
        return got
    return wait


def test_reply_not_tested_when_outbound_failed(monkeypatch):
    calls = []
    monkeypatch.setattr(pf, "wait_for_reply", reply_waiter(True, calls))
    r = pf.check_reply(ENV, sms_ok=False)
    assert r.status == "FAIL" and "sms check" in r.fix and calls == []


def test_reply_needs_operator_password(monkeypatch):
    monkeypatch.setattr(pf, "wait_for_reply", reply_waiter(True))
    r = pf.check_reply({k: v for k, v in ENV.items() if k != "OPERATOR_PASSWORD"}, sms_ok=True)
    assert r.status == "FAIL" and "OPERATOR_PASSWORD" in r.detail


def test_reply_pass_on_reply_event_and_prompt_masks_phone(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(pf, "wait_for_reply", reply_waiter(True, calls))
    r = pf.check_reply(ENV, sms_ok=True, timeout_s=7)
    assert r.status == "PASS" and "/sms/inbound" in r.detail
    assert calls == [(ENV["OPERATOR_PASSWORD"], 7)]
    err = capsys.readouterr().err
    assert "reply HELP" in err and "+1******1234" in err and ENV["DEMO_PHONE"] not in err


def test_reply_timeout_points_at_bridge(monkeypatch):
    monkeypatch.setattr(pf, "wait_for_reply", reply_waiter(False))
    r = pf.check_reply(ENV, sms_ok=True, timeout_s=5)
    assert r.status == "FAIL" and "no reply" in r.detail and "DEMO_PHONE" in r.fix and "bridge" in r.fix


def test_reply_app_unreachable(monkeypatch):
    import httpx
    monkeypatch.setattr(pf, "wait_for_reply", reply_waiter(httpx.ConnectError("refused")))
    r = pf.check_reply(ENV, sms_ok=True)
    assert r.status == "FAIL" and "refused" in r.detail and "make run" in r.fix


def test_run_checks_runs_reply_after_sms_pass(monkeypatch):
    for name in ("check_model", "check_app", "check_replay", "check_bridge", "check_consent"):
        monkeypatch.setattr(pf, name, lambda *a, n=name: pf.Result("PASS", n, "ok"))
    monkeypatch.setattr(pf, "check_sms", lambda env, ok: pf.Result("PASS", "sms", "ok"))
    seen = []
    monkeypatch.setattr(pf, "check_reply", lambda env, ok, timeout_s: seen.append((ok, timeout_s)) or
                        pf.Result("PASS", "sms-reply", "ok"))
    results = pf.run_checks({"PREFLIGHT_REPLY_TIMEOUT_S": "45"})
    assert results[-1].name == "sms-reply" and seen == [(True, 45.0)]


def _sse_app(events, logins):
    import httpx

    def handler(request):
        if request.url.path == "/login":
            logins.append(request.content)
            return httpx.Response(200, json={"status": "ok"}, headers={"set-cookie": "safesignal_session=n.s; Path=/"})
        assert request.headers.get("cookie") == "safesignal_session=n.s"
        body = "".join(f"data: {e}\n\n" for e in events)
        return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://app")


def test_wait_for_reply_sees_reply_event():
    logins, ready = [], []
    events = ['{"type": "sms", "payload": {}}', '{"type": "reply", "payload": {"keyword": "HELP"}}']
    assert pf.wait_for_reply("pw", 5, lambda: ready.append(1), client=_sse_app(events, logins)) is True
    assert ready == [1] and b'"pw"' in logins[0]


def test_wait_for_reply_ignores_other_events():
    events = ['{"type": "sms", "payload": {}}', '{"type": "consent", "payload": {}}']
    assert pf.wait_for_reply("pw", 5, lambda: None, client=_sse_app(events, [])) is False


def test_wait_for_reply_bad_password_raises():
    import httpx
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401)), base_url="http://app")
    with pytest.raises(httpx.HTTPStatusError):
        pf.wait_for_reply("wrong", 5, lambda: None, client=client)


# --- §19.7 power, sleep, hotspot ------------------------------------------------------------------

def supply(root, name, kind, online):
    d = root / name
    d.mkdir()
    (d / "type").write_text(kind + "\n")
    (d / "online").write_text(f"{online}\n")


def test_power_pass_on_ac(tmp_path):
    supply(tmp_path, "BAT0", "Battery", 1)
    supply(tmp_path, "ADP0", "Mains", 1)
    assert pf.check_power(tmp_path).status == "PASS"


def test_power_fail_on_battery_names_fix(tmp_path):
    supply(tmp_path, "ADP0", "Mains", 0)
    r = pf.check_power(tmp_path)
    assert r.status == "FAIL" and "charger" in r.fix


def test_power_skip_when_unreadable(tmp_path):
    assert pf.check_power(tmp_path / "missing").status == "SKIP"


def test_report_prints_manual_sleep_and_hotspot_items():
    out = io.StringIO()
    pf.report([pf.Result("PASS", "a", "ok")], ENV, out)
    text = out.getvalue()
    assert "MANUAL" in text and "sleep" in text and "hotspot" in text
    assert text.endswith("PREFLIGHT PASS (0 of 1 checks failed)\n")
