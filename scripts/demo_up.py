"""Start the demo stack: cloudflared tunnel + Photon Spectrum bridge + app (PRD §19.3, #29, #68).

Named tunnel when CLOUDFLARED_TUNNEL is set (PUBLIC_BASE_URL must already be its stable https URL);
otherwise a quick tunnel, whose random trycloudflare.com URL is written to .env as PUBLIC_BASE_URL.
Then starts the iMessage bridge in hackutd/ (`bun start`; skipped when PHOTON_BRIDGE_TOKEN is unset:
simulated mode) and runs the app on :8000 with .env loaded.
Ctrl-C stops both. Never prints numbers or secrets.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from preflight_checks import REPO_ROOT, load_env, missing

PORT = 8000
ENV_FILE = REPO_ROOT / ".env"
BRIDGE_DIR = REPO_ROOT / "hackutd"
QUICK_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def find_quick_url(line: str) -> str | None:
    m = QUICK_URL.search(line)
    return m.group(0) if m else None


def set_env_line(text: str, key: str, value: str) -> str:
    """Replace (or append) KEY=... in .env text, keeping every other line as is."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().removeprefix("export ").split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def start_tunnel() -> tuple[subprocess.Popen, str]:
    name = os.environ.get("CLOUDFLARED_TUNNEL", "").strip()
    if name:
        base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if not base.startswith("https://"):
            sys.exit("CLOUDFLARED_TUNNEL is set: set PUBLIC_BASE_URL in .env to that tunnel's https hostname")
        proc = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "run", "--url",
                                 f"http://localhost:{PORT}", name])
        return proc, base
    proc = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://localhost:{PORT}"],
                            stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 30
    for line in proc.stderr:
        if url := find_quick_url(line):
            threading.Thread(target=proc.stderr.read, daemon=True).start()  # drain so the pipe never fills
            ENV_FILE.write_text(set_env_line(ENV_FILE.read_text() if ENV_FILE.exists() else "",
                                             "PUBLIC_BASE_URL", url))
            return proc, url
        if time.monotonic() > deadline:
            break
    proc.kill()
    sys.exit("cloudflared quick tunnel printed no trycloudflare.com URL within 30 s")


def start_bridge() -> subprocess.Popen | None:
    if not os.environ.get("PHOTON_BRIDGE_TOKEN"):
        print("demo_up: PHOTON_BRIDGE_TOKEN unset; no Photon bridge, simulated SMS only", flush=True)
        return None
    subprocess.run(["bun", "install", "--silent"], cwd=BRIDGE_DIR, check=True)
    print("demo_up: Photon bridge (hackutd/) -> 127.0.0.1:8787", flush=True)
    return subprocess.Popen(["bun", "start"], cwd=BRIDGE_DIR)


def main() -> int:
    load_env(ENV_FILE)
    tunnel, base = start_tunnel()
    os.environ["PUBLIC_BASE_URL"] = base  # beats .env: uvicorn's --env-file never overrides set vars
    print(f"demo_up: tunnel {base} -> localhost:{PORT}", flush=True)
    bridge = start_bridge()
    try:
        app = subprocess.run(["uvicorn", "app.main:app", "--port", str(PORT),
                              *(["--env-file", str(ENV_FILE)] if ENV_FILE.exists() else [])])
        return app.returncode
    except KeyboardInterrupt:
        return 0
    finally:
        tunnel.terminate()
        if bridge:
            bridge.terminate()


if __name__ == "__main__":
    sys.exit(main())
