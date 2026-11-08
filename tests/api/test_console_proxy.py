"""The console reaches the backend only through Vite's proxy list; a route prefix missing there gets the dev
server's 404 in the browser while API tests still pass (#100: /live)."""
import re

from app import ROOT
from app.main import discover_routers


def test_vite_proxies_every_backend_route_prefix():
    cfg = (ROOT / "console" / "vite.config.ts").read_text()
    proxied = set(re.findall(r'"(/[\w-]+)"', re.search(r"const proxied = \[(.*?)\]", cfg, re.S).group(1)))
    prefixes = {"/" + route.path.split("/")[1] for router in discover_routers() for route in router.routes}
    assert prefixes <= proxied, f"add to `proxied` in console/vite.config.ts: {sorted(prefixes - proxied)}"
