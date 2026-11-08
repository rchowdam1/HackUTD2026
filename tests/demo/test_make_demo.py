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


@pytest.mark.parametrize("voice_route", [True, False])
def test_webhook_update_argv_and_read_back(monkeypatch, voice_route):
    base, number = "https://brave-otter.trycloudflare.com", "+14132883877"
    monkeypatch.setattr(demo, "live_calls", lambda: voice_route)
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        # Without the voice route the number keeps whatever voice URL it had; only smsUrl is read back.
        out = json.dumps([{"phoneNumber": number, "smsUrl": f"{base}/sms/inbound",
                           "voiceUrl": f"{base}/voice/incoming" if voice_route else "https://old.example/x"}])
        return subprocess.CompletedProcess(argv, 0, stdout=out if "phone-numbers:list" in argv else "", stderr="")
    monkeypatch.setattr(demo.subprocess, "run", run)
    demo.point_webhooks(number, base)
    voice = [f"--voice-url={base}/voice/incoming", "--voice-method=POST"] if voice_route else []
    assert calls == [
        ["twilio", "phone-numbers:update", number, *voice, f"--sms-url={base}/sms/inbound", "--sms-method=POST"],
        ["twilio", "phone-numbers:list", "-o", "json"],
    ]


def test_webhook_read_back_mismatch_aborts(monkeypatch):
    monkeypatch.setattr(demo, "live_calls", lambda: True)
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


@pytest.mark.parametrize("voice_route", [True, False])
def test_twilio_mode_uses_env_account_not_a_cli_profile(env, monkeypatch, capsys, voice_route):
    # .env credentials outrank any CLI profile, so `profiles:list` shows the env profile active and a named one
    # inactive; the old profile check aborted here before the tunnel or backend started.
    base, number = "https://brave-otter.trycloudflare.com", SECRETS["TWILIO_FROM"]
    monkeypatch.setattr(demo, "live_calls", lambda: voice_route)
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
    assert ("Call (413) 288-3877 to start a live call" in out) == voice_route
    assert ("Live calls: not in this build" in out) != voice_route
    assert demo.os.environ["PUBLIC_BASE_URL"] == base
