"""scripts/demo_up.py: startup order and cleanup with fake processes (no uvicorn, no bun, no Photon)."""
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
    started = []
    monkeypatch.setattr(du, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(du, "load_env", lambda path: None)
    monkeypatch.setattr(du.subprocess, "Popen", lambda cmd, **kw: started.append(FakeProc(cmd)) or started[-1])
    return started


def test_never_starts_a_tunnel_and_binds_localhost(stack, monkeypatch):
    monkeypatch.delenv("PHOTON_BRIDGE_TOKEN", raising=False)
    monkeypatch.setattr(du, "wait_healthy", lambda app, url, timeout_s=120: True)
    assert du.main() == 0
    assert [p.cmd[0] for p in stack] == ["uvicorn"]
    assert "--host" in stack[0].cmd and stack[0].cmd[stack[0].cmd.index("--host") + 1] == "127.0.0.1"


def test_bridge_starts_only_after_app_is_healthy(stack, monkeypatch):
    monkeypatch.setenv("PHOTON_BRIDGE_TOKEN", "t")
    monkeypatch.setattr(du.subprocess, "run", lambda *a, **kw: None)
    order = []
    monkeypatch.setattr(du, "wait_healthy", lambda app, url, timeout_s=120: order.append(len(stack)) or True)
    du.main()
    assert order == [1] and [p.cmd[0] for p in stack] == ["uvicorn", "bun"]
    assert all(p.terminated for p in stack)


def test_unhealthy_app_skips_bridge_and_stops_app(stack, monkeypatch):
    monkeypatch.setenv("PHOTON_BRIDGE_TOKEN", "t")
    monkeypatch.setattr(du, "wait_healthy", lambda app, url, timeout_s=120: False)
    assert du.main() == 1
    assert [p.cmd[0] for p in stack] == ["uvicorn"] and stack[0].terminated


def test_bridge_install_failure_still_stops_app(stack, monkeypatch):
    monkeypatch.setenv("PHOTON_BRIDGE_TOKEN", "t")
    monkeypatch.setattr(du, "wait_healthy", lambda app, url, timeout_s=120: True)

    def no_bun(*a, **kw):
        raise FileNotFoundError("bun")
    monkeypatch.setattr(du.subprocess, "run", no_bun)
    with pytest.raises(FileNotFoundError):
        du.main()
    assert stack[0].terminated


def test_wait_healthy_gives_up_when_app_exits():
    proc = FakeProc(["uvicorn"])
    proc.code = 1
    assert du.wait_healthy(proc, "http://127.0.0.1:9/health", timeout_s=5) is False


def test_wait_healthy_times_out():
    assert du.wait_healthy(FakeProc(["uvicorn"]), "http://127.0.0.1:9/health", timeout_s=0.3) is False
