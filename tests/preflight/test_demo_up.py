"""scripts/demo_up.py pure helpers: tunnel URL parsing and the .env line rewrite."""
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))  # demo_up imports preflight_checks
_spec = importlib.util.spec_from_file_location("demo_up", SCRIPTS / "demo_up.py")
du = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(du)

LOG = """INF Requesting new quick Tunnel on trycloudflare.com...
INF +--------------------------------------------------------------------------------------------+
INF |  Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):  |
INF |  https://bright-owl-shape-test.trycloudflare.com                                           |
"""


def test_tunnel_url_parsed_from_cloudflared_log():
    assert du.tunnel_url(LOG) == "https://bright-owl-shape-test.trycloudflare.com"
    assert du.tunnel_url("ERR failed to request https://api.trycloudflare.com/tunnel") is None


def test_set_env_line_replaces_or_appends():
    text = "A=1\nPUBLIC_BASE_URL=\nB=2\n"
    assert du.set_env_line(text, "PUBLIC_BASE_URL", "https://x.trycloudflare.com") == \
        "A=1\nPUBLIC_BASE_URL=https://x.trycloudflare.com\nB=2\n"
    assert du.set_env_line("A=1", "PUBLIC_BASE_URL", "https://y") == "A=1\nPUBLIC_BASE_URL=https://y\n"
