"""Demo bring-up (PRD §19.7). Entry point: `scripts/demo_up`; Ctrl-C stops everything it started.

1. cloudflared quick tunnel to :8000, URL parsed from its log (it changes on every start).
2. PUBLIC_BASE_URL=<url> written to .env, so `scripts/preflight` and Twilio signature checks agree.
3. Backend (uvicorn app.main:app, port 8000) started with .env + that PUBLIC_BASE_URL.
4. If TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_FROM are set, the number's SMS webhook = POST <url>/sms/inbound.
Never prints secrets or full phone numbers.
"""
from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import time

import httpx

from preflight_checks import REPO_ROOT, TWILIO_VARS, load_env, mask_phone, missing, scrub

ENV_FILE = REPO_ROOT / ".env"
TUNNEL_LOG = REPO_ROOT / "data" / "demo_up_tunnel.log"
PORT = 8000
URL_RE = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com")


def tunnel_url(log: str) -> str | None:
    m = URL_RE.search(log)
    return m.group() if m else None


def set_env_line(text: str, key: str, value: str) -> str:
    new, n = re.subn(rf"^{key}=.*$", lambda _: f"{key}={value}", text, flags=re.M)
    return new if n else text.rstrip("\n") + f"\n{key}={value}\n"


def port_open(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for(what: str, fn, timeout_s: float):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if value := fn():
                return value
        except httpx.HTTPError:
            pass
        time.sleep(1)
    sys.exit(f"demo_up: timed out after {timeout_s:.0f}s waiting for {what}")


def health(url: str) -> bool:
    r = httpx.get(url + "/health", timeout=5)
    return r.status_code == 200 and r.json().get("status") == "ok"


def set_twilio_webhook(env: dict, url: str) -> str:
    if need := missing(env, TWILIO_VARS):
        return f"SKIP Twilio webhook: not set in .env: {', '.join(need)} (rerun demo_up after filling them)"
    from twilio.rest import Client
    client = Client(env["TWILIO_ACCOUNT_SID"], env["TWILIO_AUTH_TOKEN"])
    numbers = client.incoming_phone_numbers.list(phone_number=env["TWILIO_FROM"], limit=1)
    if not numbers:
        return "FAIL Twilio webhook: TWILIO_FROM is not a number on this Twilio account"
    numbers[0].update(sms_url=url + "/sms/inbound", sms_method="POST")
    return f"OK Twilio webhook for {mask_phone(env['TWILIO_FROM'])} = POST {url}/sms/inbound"


def main() -> int:
    if port_open(PORT):
        sys.exit(f"demo_up: something is already on :{PORT}. Stop it (e.g. `make run`) first: the backend must "
                 "start with the new PUBLIC_BASE_URL or Twilio signatures fail.")
    if not ENV_FILE.is_file():
        sys.exit("demo_up: no .env; `cp .env.example .env` and fill it")
    procs = []
    try:
        TUNNEL_LOG.parent.mkdir(exist_ok=True)
        with open(TUNNEL_LOG, "w") as log:
            procs.append(subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "--url",
                                           f"http://localhost:{PORT}"], stdout=log, stderr=subprocess.STDOUT))
        url = wait_for("the cloudflared quick-tunnel URL", lambda: tunnel_url(TUNNEL_LOG.read_text()), 60)
        ENV_FILE.write_text(set_env_line(ENV_FILE.read_text(), "PUBLIC_BASE_URL", url))
        print(f"OK tunnel {url} (PUBLIC_BASE_URL written to .env)", flush=True)

        load_env(ENV_FILE)
        os.environ["PUBLIC_BASE_URL"] = url  # .env wins over a stale exported value
        procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
                                      cwd=REPO_ROOT))
        wait_for("the backend on :8000", lambda: health(f"http://127.0.0.1:{PORT}"), 180)
        wait_for(f"{url}/health through the tunnel", lambda: health(url), 90)
        print(f"OK backend on :{PORT}, {url}/health ok", flush=True)

        print(scrub(set_twilio_webhook(dict(os.environ), url), dict(os.environ)), flush=True)
        print("Next: text YES from DEMO_PHONE and SPARE_PHONE to the Twilio number, then in another terminal run "
              "`scripts/preflight` and reply HELP from DEMO_PHONE when asked. Ctrl-C here stops tunnel + backend.",
              flush=True)
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        print("demo_up: tunnel or backend exited; shutting down", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()


def _on_sigterm(*_):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _on_sigterm)
    sys.exit(main())
