"""Start the demo stack: cloudflared tunnel -> PUBLIC_BASE_URL -> Twilio webhook -> app (PRD §19.3, #29).

Named tunnel when CLOUDFLARED_TUNNEL is set (PUBLIC_BASE_URL must already be its stable https URL);
otherwise a quick tunnel, whose random trycloudflare.com URL is written to .env as PUBLIC_BASE_URL.
Then points the TWILIO_FROM number's "A message comes in" webhook at PUBLIC_BASE_URL/sms/inbound
(skipped when Twilio vars are unset: simulated mode) and runs the app on :8000 with .env loaded.
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

from preflight_checks import REPO_ROOT, TWILIO_VARS, load_env, missing

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


def point_webhook(base: str) -> None:
    need = missing(dict(os.environ), TWILIO_VARS)
    if need:
        print(f"demo_up: Twilio webhook not set ({', '.join(need)} unset); simulated SMS only", flush=True)
        return
    from twilio.rest import Client
    client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    numbers = client.incoming_phone_numbers.list(phone_number=os.environ["TWILIO_FROM"], limit=1)
    if not numbers:
        sys.exit("TWILIO_FROM is not a phone number on this Twilio account")
    numbers[0].update(sms_url=f"{base}/sms/inbound", sms_method="POST")
    print(f"demo_up: Twilio SMS webhook = POST {base}/sms/inbound", flush=True)


def main() -> int:
    load_env(ENV_FILE)
    tunnel, base = start_tunnel()
    os.environ["PUBLIC_BASE_URL"] = base  # beats .env: uvicorn's --env-file never overrides set vars
    print(f"demo_up: tunnel {base} -> localhost:{PORT}", flush=True)
    try:
        point_webhook(base)
        app = subprocess.run(["uvicorn", "app.main:app", "--port", str(PORT),
                              *(["--env-file", str(ENV_FILE)] if ENV_FILE.exists() else [])])
        return app.returncode
    except KeyboardInterrupt:
        return 0
    finally:
        tunnel.terminate()


if __name__ == "__main__":
    sys.exit(main())
