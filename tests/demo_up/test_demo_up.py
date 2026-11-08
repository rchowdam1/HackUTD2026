"""scripts/demo_up.py pure helpers: no cloudflared, no Photon."""
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))  # demo_up imports preflight_checks


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = sys.modules[name] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


du = _load("demo_up")


def test_find_quick_url_in_cloudflared_log():
    line = "2026-11-08T01:00:00Z INF |  https://brave-otter-12-x.trycloudflare.com                |"
    assert du.find_quick_url(line) == "https://brave-otter-12-x.trycloudflare.com"
    assert du.find_quick_url("INF Starting tunnel") is None


def test_set_env_line_replaces_only_that_key():
    text = "# Photon\nPHOTON_PROJECT_ID=pho_prj_x\nPUBLIC_BASE_URL=https://old.trycloudflare.com\nX=1\n"
    out = du.set_env_line(text, "PUBLIC_BASE_URL", "https://new.trycloudflare.com")
    assert out == "# Photon\nPHOTON_PROJECT_ID=pho_prj_x\nPUBLIC_BASE_URL=https://new.trycloudflare.com\nX=1\n"


def test_set_env_line_appends_when_missing():
    assert du.set_env_line("X=1\n", "PUBLIC_BASE_URL", "https://a.trycloudflare.com") == \
        "X=1\nPUBLIC_BASE_URL=https://a.trycloudflare.com\n"
    assert du.set_env_line("", "K", "v") == "K=v\n"
