"""scripts/demo.py (`make demo`) with fakes: no Twilio CLI, cloudflared, uvicorn, vite or whisper is started."""

import json
import socket
import subprocess

import pytest

from conftest import load_script

demo = load_script("demo")

SECRETS = {
    "TWILIO_ACCOUNT_SID": "AC" + "1" * 32, "TWILIO_AUTH_TOKEN": "tok-secret-123", "TWILIO_FROM": "+14132883877",
    "DEMO_PHONE": "+15550001111", "SPARE_PHONE": "+15550002222", "OPERATOR_PASSWORD": "pw-secret-456",
    "SESSION_SECRET": "sess-secret-789", "CONSENT_SALT": "salt-secret-000", "OPENROUTER_API_KEY": "sk-or-secret",
}


@pytest.fixture
def env(monkeypatch):
    for k in demo.KEYS + ("DEMO_PORT", "CONSOLE_PORT", "REPLAY_SOURCE"):
        monkeypatch.setenv(k, "")  # records the original, so what main() sets is undone after the test
        monkeypatch.delenv(k)
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(demo, "load_env", lambda path: None)
    monkeypatch.setattr(demo.signal, "signal", lambda sig, handler: None)  # keep pytest's own handlers


def test_key_table_says_set_or_empty_never_values(env):
    table = demo.key_table(dict(demo.os.environ))
    for value in SECRETS.values():
        assert value not in table
    assert "TWILIO_AUTH_TOKEN" in table and " set" in table
    assert [line.split()[-1] for line in table.splitlines() if "INTENT_MODEL" in line] == ["EMPTY"]


@pytest.mark.parametrize("unset, twilio", [("SESSION_SECRET", False), ("DEMO_PHONE", True)])
def test_missing_key_aborts_before_anything_starts(env, monkeypatch, unset, twilio):
    monkeypatch.delenv(unset)
    monkeypatch.setattr(demo.subprocess, "run", lambda *a, **k: pytest.fail("nothing may run"))
    with pytest.raises(SystemExit, match=unset):
        demo.main([] if twilio else ["--no-twilio"])


def test_no_twilio_does_not_need_twilio_keys(env, monkeypatch):
    monkeypatch.delenv("DEMO_PHONE")
    demo.check_keys(dict(demo.os.environ), twilio=False)


def test_busy_port_falls_back_to_first_free():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        taken = busy.getsockname()[1]
        assert not demo.port_free(taken)
        got = demo.pick_port(taken, taken + 1)
    assert got > taken and demo.port_free(got)


def test_webhook_update_argv_and_read_back(monkeypatch):
    base, number = "https://brave-otter.trycloudflare.com", "+14132883877"
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        out = json.dumps([{"phoneNumber": number, "smsUrl": f"{base}/sms/inbound", "voiceUrl": f"{base}/voice/incoming"}])
        return subprocess.CompletedProcess(argv, 0, stdout=out if "phone-numbers:list" in argv else "", stderr="")
    monkeypatch.setattr(demo.subprocess, "run", run)
    demo.point_webhooks(number, base)
    assert calls == [
        ["twilio", "phone-numbers:update", number, f"--voice-url={base}/voice/incoming", "--voice-method=POST",
         f"--sms-url={base}/sms/inbound", "--sms-method=POST"],
        ["twilio", "phone-numbers:list", "-o", "json"],
    ]


def test_webhook_read_back_mismatch_aborts(monkeypatch):
    stale = json.dumps([{"phoneNumber": "+14132883877", "voiceUrl": "https://old.example/voice/incoming",
                         "smsUrl": "https://old.example/sms/inbound"}])
    monkeypatch.setattr(demo.subprocess, "run",
                        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout=stale, stderr=""))
    with pytest.raises(SystemExit, match="smsUrl, voiceUrl"):
        demo.point_webhooks("+14132883877", "https://new.trycloudflare.com")


class FakeProc:
    pid = 0

    def __init__(self, cmd, **kw):
        self.cmd = cmd

    def poll(self):
        raise KeyboardInterrupt  # presenter presses Ctrl-C once the stack is up


def test_no_twilio_skips_tunnel_and_twilio_cli(env, monkeypatch, capsys):
    ran, spawned, stopped = [], [], []
    monkeypatch.setattr(demo.shutil, "which", lambda name: pytest.fail(f"looked up {name}"))
    monkeypatch.setattr(demo.demo_up, "start_tunnel", lambda: pytest.fail("tunnel started"))
    monkeypatch.setattr(demo.subprocess, "run",
                        lambda argv, **kw: ran.append(argv) or subprocess.CompletedProcess(argv, 0))
    monkeypatch.setattr(demo, "spawn", lambda cmd, **kw: spawned.append(FakeProc(cmd, **kw)) or spawned[-1])
    monkeypatch.setattr(demo.demo_up, "wait_healthy", lambda proc, url, timeout_s=120: True)
    monkeypatch.setattr(demo, "port_free", lambda port: port not in (8000, 5173))
    monkeypatch.setattr(demo, "stop", lambda procs: stopped.extend(procs))

    assert demo.main(["--no-twilio"]) == 0

    assert not any(argv[0] in ("twilio", "tailscale", "cloudflared") for argv in ran)
    assert [p.cmd[0] for p in spawned] == ["uvicorn", "npx"]
    assert spawned[0].cmd[spawned[0].cmd.index("--port") + 1] == "8010"
    assert spawned[1].cmd[spawned[1].cmd.index("--port") + 1] == "5180"
    assert stopped == spawned
    assert demo.os.environ["REPLAY_SOURCE"] == "asr" and demo.os.environ["INTENT_MODEL"] == "on"
    out = capsys.readouterr().out
    assert "port 8000 is busy: backend on 8010" in out and "http://127.0.0.1:5180" in out
    assert "Arm:      C (rules + AI)" in out
    for value in SECRETS.values():
        assert value not in out
    assert "(413) 288-3877" not in out  # no live-call line without Twilio


def test_twilio_mode_uses_env_account_not_a_cli_profile(env, monkeypatch, capsys):
    # .env credentials outrank any CLI profile, so `profiles:list` shows the env profile active and a named one
    # inactive; the old profile check aborted here before the tunnel or backend started.
    base, number = "https://brave-otter.trycloudflare.com", SECRETS["TWILIO_FROM"]
    ran = []

    def run(argv, **kw):
        ran.append(argv)
        out = ""
        if argv[:2] == ["twilio", "profiles:list"]:
            out = "ID      Account SID  Active\n[env]   AC111        true\nAmeya   AC222        false\n"
        elif argv[:2] == ["twilio", "phone-numbers:list"]:
            out = json.dumps([{"phoneNumber": number, "voiceUrl": f"{base}/voice/incoming",
                               "smsUrl": f"{base}/sms/inbound"}])
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")
    monkeypatch.setattr(demo.subprocess, "run", run)
    monkeypatch.setattr(demo.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr(demo.demo_up, "start_tunnel", lambda: (FakeProc(["cloudflared"]), base))
    monkeypatch.setattr(demo, "spawn", lambda cmd, **kw: FakeProc(cmd, **kw))
    monkeypatch.setattr(demo.demo_up, "wait_healthy", lambda proc, url, timeout_s=120: True)
    monkeypatch.setattr(demo, "tunnel_answers", lambda b: True)
    monkeypatch.setattr(demo, "stop", lambda procs: None)

    assert demo.main([]) == 0

    assert not any(argv[:2] == ["twilio", "profiles:use"] or argv[:2] == ["twilio", "profiles:list"] for argv in ran)
    assert demo.webhook_argv(number, base) in ran
    out = capsys.readouterr().out
    assert "Call (413) 288-3877 to start a live call" in out
    assert demo.os.environ["PUBLIC_BASE_URL"] == base


class DeadProc(FakeProc):
    def poll(self):
        return 1


def test_dead_quick_tunnel_is_replaced_and_the_number_repointed(env, monkeypatch):
    # A quick tunnel comes back with a new hostname; the backend checks Twilio signatures against it, so it restarts.
    old, new = "https://old-otter.trycloudflare.com", "https://new-otter.trycloudflare.com"
    pointed, stopped = [], []
    monkeypatch.setattr(demo.demo_up, "start_tunnel", lambda: (FakeProc(["cloudflared"]), new))
    monkeypatch.setattr(demo, "spawn", lambda cmd, **kw: FakeProc(cmd, **kw))
    monkeypatch.setattr(demo.demo_up, "wait_healthy", lambda proc, url, timeout_s=120: True)
    monkeypatch.setattr(demo, "tunnel_answers", lambda b: True)
    monkeypatch.setattr(demo, "point_webhooks", lambda number, base: pointed.append(base))
    monkeypatch.setattr(demo, "stop", lambda procs: stopped.extend(procs))
    app = DeadProc(["uvicorn"])

    tunnel, new_app, base = demo.recover_tunnel(8000, app, old)

    assert base == new and demo.os.environ["PUBLIC_BASE_URL"] == new and pointed == [new]
    assert stopped == [app] and new_app.cmd[0] == "uvicorn" and tunnel.cmd == ["cloudflared"]


def test_webhooks_stay_put_when_the_tunnel_does_not_answer(env, monkeypatch):
    monkeypatch.setattr(demo, "tunnel_answers", lambda b: False)
    monkeypatch.setattr(demo, "point_webhooks", lambda number, base: pytest.fail("pointed at a dead tunnel"))
    demo.expose("https://dead.trycloudflare.com")


def test_tunnel_check_resolves_through_public_dns_and_connects_by_ip(monkeypatch):
    # The laptop's resolver may have cached "not found" for a brand-new quick-tunnel hostname; Twilio uses public DNS.
    host, seen = "brave-otter.trycloudflare.com", []

    class Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, url, headers, extensions):
            seen.append((url, headers, extensions))
            return type("R", (), {"status_code": 200})()
    monkeypatch.setattr(demo, "public_ip", lambda h: "104.16.230.132" if h == host else None)
    monkeypatch.setattr(demo.httpx, "Client", Client)
    assert demo.tunnel_answers(f"https://{host}")
    assert seen == [("https://104.16.230.132/health", {"Host": host}, {"sni_hostname": host})]
    monkeypatch.setattr(demo.time, "sleep", lambda s: None)
    assert not demo.tunnel_answers("https://gone.trycloudflare.com", timeout_s=0.05)
