"""Start the demo stack: app on 127.0.0.1:8000 + Photon Spectrum bridge (PRD §19.3, #68).

Nothing is published to the internet: the bridge reaches Photon over the SDK's own outbound
connection, so no tunnel or public webhook is needed (docs/photon-live.md). The app starts first and
the bridge only once /health answers, so inbound texts (STOP) are not dropped at startup. The bridge
is skipped when PHOTON_BRIDGE_TOKEN is unset (simulated SMS only).
Ctrl-C stops both. Never prints numbers or secrets.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request

from preflight_checks import REPO_ROOT, load_env

PORT = 8000
ENV_FILE = REPO_ROOT / ".env"
BRIDGE_DIR = REPO_ROOT / "hackutd"


def wait_healthy(app: subprocess.Popen, url: str, timeout_s: float = 120) -> bool:
    """Poll url until it answers 200, the app exits, or timeout_s passes."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and app.poll() is None:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def start_bridge() -> subprocess.Popen | None:
    if not os.environ.get("PHOTON_BRIDGE_TOKEN"):
        print("demo_up: PHOTON_BRIDGE_TOKEN unset; no Photon bridge, simulated SMS only", flush=True)
        return None
    subprocess.run(["bun", "install", "--silent"], cwd=BRIDGE_DIR, check=True)
    print("demo_up: Photon bridge (hackutd/) -> 127.0.0.1:8787", flush=True)
    return subprocess.Popen(["bun", "start"], cwd=BRIDGE_DIR)


def main() -> int:
    load_env(ENV_FILE)
    procs: list[subprocess.Popen] = []
    try:
        app = subprocess.Popen(["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT),
                                *(["--env-file", str(ENV_FILE)] if ENV_FILE.exists() else [])])
        procs.append(app)
        if not wait_healthy(app, f"http://127.0.0.1:{PORT}/health"):
            print("demo_up: app did not become healthy; not starting the bridge", file=sys.stderr, flush=True)
            return 1
        print(f"demo_up: app on http://127.0.0.1:{PORT} (localhost only)", flush=True)
        bridge = start_bridge()
        if bridge:
            procs.append(bridge)
        return app.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        for proc in reversed(procs):
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
