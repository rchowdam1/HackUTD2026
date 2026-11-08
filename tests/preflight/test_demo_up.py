"""scripts/demo_up.py + sms_kill_check.py pure helpers: no cloudflared, no Twilio."""
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))  # both scripts import preflight_checks


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = sys.modules[name] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


du, kc = _load("demo_up"), _load("sms_kill_check")


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


def test_kill_check_summary():
    res = [("delivered", 2.0, 1), ("delivered", 4.0, 1), ("delivered", 9.0, 2), ("undelivered", 120.0, 1)]
    assert kc.summary(res) == "3/4 delivered; median 4.0 s, worst 9.0 s; segments [1, 2]"
    assert kc.summary([("failed", 1.0, 1)]) == "0/1 delivered; segments [1]"
