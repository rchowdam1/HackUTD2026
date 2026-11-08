"""scripts/demo_up.py: startup order, cleanup and .env helpers with fakes (no cloudflared, no uvicorn, no Twilio)."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))  # demo_up imports preflight_checks


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = sys.modules[name] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


du = _load("demo_up")


class FakeProc:
    def __init__(self, cmd, **kw):
        self.cmd, self.terminated, self.code = cmd, False, None

    def poll(self):
        return self.code

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


@pytest.fixture
def stack(monkeypatch, tmp_path):
    """Fake Popen + a fake quick tunnel at TUNNEL; records every process started and webhook pointed."""
    started, hooks = [], []
    monkeypatch.setattr(du, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(du, "load_env", lambda path: None)
    monkeypatch.setattr(du.subprocess, "Popen", lambda cmd, **kw: started.append(FakeProc(cmd)) or started[-1])
    monkeypatch.setattr(du, "start_tunnel", lambda: (du.subprocess.Popen(["cloudflared"]), TUNNEL))
    monkeypatch.setattr(du, "point_webhook", lambda base: hooks.append((len(started), base)))
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    return started, hooks


TUNNEL = "https://brave-otter.trycloudflare.com"


def test_tunnel_then_app_on_localhost_then_webhook(stack, monkeypatch):
    started, hooks = stack
    order = []
    monkeypatch.setattr(du, "wait_healthy", lambda app, url, timeout_s=120: order.append(len(started)) or True)
    assert du.main() == 0
    assert [p.cmd[0] for p in started] == ["cloudflared", "uvicorn"]
    app = started[1].cmd
    assert app[app.index("--host") + 1] == "127.0.0.1"
    assert order == [2] and hooks == [(2, TUNNEL)]  # webhook only once the app is healthy
    assert du.os.environ["PUBLIC_BASE_URL"] == TUNNEL
    assert all(p.terminated for p in started)


def test_unhealthy_app_skips_webhook_and_stops_everything(stack, monkeypatch):
    started, hooks = stack
    monkeypatch.setattr(du, "wait_healthy", lambda app, url, timeout_s=120: False)
    assert du.main() == 1
    assert hooks == [] and all(p.terminated for p in started)


def test_webhook_failure_still_stops_everything(stack, monkeypatch):
    started, _ = stack
    monkeypatch.setattr(du, "wait_healthy", lambda app, url, timeout_s=120: True)

    def bad_number(base):
        raise SystemExit("TWILIO_FROM is not a phone number on this Twilio account")
    monkeypatch.setattr(du, "point_webhook", bad_number)
    with pytest.raises(SystemExit):
        du.main()
    assert all(p.terminated for p in started)


def test_webhook_skipped_without_twilio_vars(monkeypatch, capsys):
    for var in du.TWILIO_VARS:
        monkeypatch.delenv(var, raising=False)
    du.point_webhook(TUNNEL)
    assert "simulated SMS only" in capsys.readouterr().out


def test_find_quick_url_in_cloudflared_log():
    line = "2026-11-08T01:00:00Z INF |  https://brave-otter-12-x.trycloudflare.com                |"
    assert du.find_quick_url(line) == "https://brave-otter-12-x.trycloudflare.com"
    assert du.find_quick_url("INF Starting tunnel") is None


def test_set_env_line_replaces_only_that_key():
    text = "# Twilio\nTWILIO_FROM=+15550001111\nPUBLIC_BASE_URL=https://old.trycloudflare.com\nX=1\n"
    out = du.set_env_line(text, "PUBLIC_BASE_URL", "https://new.trycloudflare.com")
    assert out == "# Twilio\nTWILIO_FROM=+15550001111\nPUBLIC_BASE_URL=https://new.trycloudflare.com\nX=1\n"


def test_set_env_line_appends_when_missing():
    assert du.set_env_line("X=1\n", "PUBLIC_BASE_URL", "https://a.trycloudflare.com") == \
        "X=1\nPUBLIC_BASE_URL=https://a.trycloudflare.com\n"
    assert du.set_env_line("", "K", "v") == "K=v\n"


def test_wait_healthy_gives_up_when_app_exits():
    proc = FakeProc(["uvicorn"])
    proc.code = 1
    assert du.wait_healthy(proc, "http://127.0.0.1:9/health", timeout_s=5) is False


def test_wait_healthy_times_out():
    assert du.wait_healthy(FakeProc(["uvicorn"]), "http://127.0.0.1:9/health", timeout_s=0.3) is False
