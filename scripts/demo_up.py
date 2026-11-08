"""Start the demo stack: cloudflared tunnel -> PUBLIC_BASE_URL -> app on 127.0.0.1:8000 -> Twilio webhook
(PRD §19.3, #78, docs/twilio-live.md).

Named tunnel when CLOUDFLARED_TUNNEL is set (PUBLIC_BASE_URL must already be its stable https URL);
otherwise a quick tunnel, whose random trycloudflare.com URL is written to .env as PUBLIC_BASE_URL.
The app only answers /sms/inbound, /sms/status and /health through the tunnel (app.main), so the
operator console and API stay local. Once /health answers, the TWILIO_FROM number's "A message comes in"
webhook is pointed at PUBLIC_BASE_URL/sms/inbound, so inbound texts (STOP) are not dropped at startup
(skipped when Twilio vars are unset: simulated SMS only).
Ctrl-C stops both. Never prints numbers or secrets.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

from preflight_checks import REPO_ROOT, TWILIO_VARS, load_env, missing, twilio_number

PORT = 8000
ENV_FILE = REPO_ROOT / ".env"
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
    target = f"http://127.0.0.1:{PORT}"
    name = os.environ.get("CLOUDFLARED_TUNNEL", "").strip()
    if name:
        base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if not base.startswith("https://"):
            sys.exit("CLOUDFLARED_TUNNEL is set: set PUBLIC_BASE_URL in .env to that tunnel's https hostname")
        return subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "run", "--url", target, name]), base
    proc = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "--url", target],
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


def point_webhook(base: str) -> None:
    need = missing(dict(os.environ), TWILIO_VARS)
    if need:
        print(f"demo_up: Twilio webhook not set ({', '.join(need)} unset); simulated SMS only", flush=True)
        return
    number = twilio_number(dict(os.environ))
    if number is None:
        sys.exit("TWILIO_FROM is not a phone number on this Twilio account")
    number.update(sms_url=f"{base}/sms/inbound", sms_method="POST")
    print(f"demo_up: Twilio SMS webhook = POST {base}/sms/inbound", flush=True)


def main() -> int:
    load_env(ENV_FILE)
    procs: list[subprocess.Popen] = []
    try:
        tunnel, base = start_tunnel()
        procs.append(tunnel)
        os.environ["PUBLIC_BASE_URL"] = base  # beats .env: uvicorn's --env-file never overrides set vars
        print(f"demo_up: tunnel {base} -> 127.0.0.1:{PORT} (only /sms/inbound, /sms/status, /health)", flush=True)
        app = subprocess.Popen(["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT),
                                *(["--env-file", str(ENV_FILE)] if ENV_FILE.exists() else [])])
        procs.append(app)
        if not wait_healthy(app, f"http://127.0.0.1:{PORT}/health"):
            print("demo_up: app did not become healthy; not pointing the Twilio webhook", file=sys.stderr, flush=True)
            return 1
        print(f"demo_up: app on http://127.0.0.1:{PORT}", flush=True)
        point_webhook(base)
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
