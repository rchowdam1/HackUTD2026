"""Preflight checks run before every judging block (PRD §19.7). Entry point: `scripts/preflight [--no-sms]`.

Prints one line per check, `PASS|FAIL|SKIP <name> - <detail>`, with a `fix:` line under
each FAIL, and exits 1 if anything failed. Reads `.env` at the repo root (existing
environment wins). Secret values and phone numbers are never printed.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SECRET_VARS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "CONSENT_SALT", "OPERATOR_PASSWORD", "SESSION_SECRET")
PHONE_VARS = ("TWILIO_FROM", "DEMO_PHONE", "SPARE_PHONE")
TWILIO_VARS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM")
# Routes the live demo needs (docs/track-b-brief.md), with the task that adds them.
DEMO_ROUTES = {
    "/sms/inbound": "b-sms #17", "/sms/status": "b-sms #17", "/login": "b-api #19",
    "/events/stream": "b-api #19", "/demo/run/{scenario_id}": "b-api #19", "/demo/reset": "b-api #19",
}
DEMO_ALERTS = {"bank": ["ALERT-OTP-01"], "clinic": []}  # expected decisions per cached demo replay
MODEL_DOWNLOAD = ("uv run python -c \"from faster_whisper import WhisperModel; "
                  "WhisperModel('small.en', device='cpu', compute_type='int8')\"  (once, online)")
SMS_TIMEOUT_S = 30


@dataclass
class Result:
    status: str  # PASS | FAIL | SKIP
    name: str
    detail: str
    fix: str = ""


def load_env(path: Path) -> None:
    """Minimal .env parser: KEY=VALUE lines, # comments, optional quotes. Never overrides os.environ."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def mask_phone(number: str) -> str:
    return number[:2] + "*" * max(len(number) - 6, 0) + number[-4:] if len(number) > 6 else "***"


def scrub(text: str, env: dict) -> str:
    """Remove secret values, Twilio account SIDs and phone numbers from text before printing."""
    for var in SECRET_VARS:
        if len(env.get(var) or "") >= 4:
            text = text.replace(env[var], "***")
    text = re.sub(r"AC[0-9a-fA-F]{32}", "AC***", text)
    return re.sub(r"\+\d{8,15}", lambda m: mask_phone(m.group()), text)


def missing(env: dict, names) -> list[str]:
    return [n for n in names if not (env.get(n) or "").strip()]


# --- checks -------------------------------------------------------------------------------------

def check_model() -> Result:
    from app import asr, ingest
    t0 = time.monotonic()
    try:
        asr.load_model()
    except Exception as e:
        return Result("FAIL", "model", f"faster-whisper {asr.MODEL_NAME} not loadable offline: {e}",
                      f"download it: {MODEL_DOWNLOAD}")
    detail = f"faster-whisper {asr.MODEL_NAME} loaded offline in {time.monotonic() - t0:.1f}s"
    if asr.default_source() != "asr":
        return Result("PASS", "model", detail + "; note: REPLAY_SOURCE is not asr, demo replays use cached transcripts")
    no_audio = [sid for sid in DEMO_ALERTS if not _has_audio(ingest, sid)]
    note = f"; note: no audio for {', '.join(no_audio)}, those replay cached" if no_audio else ", demo audio present"
    return Result("PASS", "model", detail + note)


def _has_audio(ingest, scenario_id: str) -> bool:
    from app.models import Scenario
    s = Scenario.model_validate_json((ingest.DEMO_DIR / f"{scenario_id}.json").read_text())
    return all(t.audio and (ingest.AUDIO_DIR / t.audio).is_file() for t in s.turns)


def check_app() -> Result:
    """App starts (lifespan: storage.init + ASR preload) with HF offline, /health ok, demo routes mounted."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/health")
    if r.status_code != 200 or r.json().get("status") != "ok":
        return Result("FAIL", "app-offline", f"/health returned {r.status_code} {r.text[:80]}",
                      "run `make run` and read the startup traceback")
    paths = {getattr(route, "path", "") for route in app.routes}
    absent = [p for p in DEMO_ROUTES if p not in paths]
    if absent:
        owners = sorted({DEMO_ROUTES[p] for p in absent})
        return Result("FAIL", "app-offline", f"app starts offline but routes are missing: {', '.join(absent)}",
                      f"needs {', '.join(owners)} merged to main")
    return Result("PASS", "app-offline", "app starts offline, /health ok, demo routes mounted")


class _NullGateway:
    def send(self, template_id: str, session_ref: str) -> str:
        return "PREFLIGHT"


async def _replay(scenario_id: str) -> tuple[int, list[str]]:
    from app import ingest
    from app.events import hub
    async with hub.subscribe() as q:
        await ingest.run(scenario_id, realtime=False, source="cached")
        events = [q.get_nowait() for _ in range(q.qsize())]
    segments = [e for e in events if e.type == "segment" and e.payload["source"] == "cached"]
    return len(segments), [e.payload["template_id"] for e in events if e.type == "decision"]


def check_replay() -> Result:
    from app import sms
    async def replay_all() -> dict:
        return {sid: await _replay(sid) for sid in DEMO_ALERTS}

    with mock.patch.object(sms, "get_gateway", _NullGateway):  # never text anyone from a test replay
        got = asyncio.run(replay_all())
    bad = [f"{sid}: {n} segments, decisions {alerts}" for sid, (n, alerts) in got.items()
           if n == 0 or alerts != DEMO_ALERTS[sid]]
    if bad:
        return Result("FAIL", "cached-replay", "; ".join(bad) + f" (expected {DEMO_ALERTS})",
                      "check scenarios/demo/<id>/transcript.json and policy/v1.0 rules; run `make smoke`")
    return Result("PASS", "cached-replay",
                  f"bank {got['bank'][0]} segments -> ALERT-OTP-01; clinic {got['clinic'][0]} segments -> no alert")


def http_get(url: str):
    import httpx
    return httpx.get(url, timeout=10, follow_redirects=False)


def check_tunnel(env: dict) -> Result:
    base = (env.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return Result("FAIL", "tunnel", "PUBLIC_BASE_URL is not set",
                      "set PUBLIC_BASE_URL in .env to the named cloudflared tunnel URL (https://...)")
    if not base.startswith("https://"):
        return Result("FAIL", "tunnel", f"PUBLIC_BASE_URL is not https: {base}",
                      "use the https tunnel URL (Twilio signatures are validated against it)")
    try:
        r = http_get(base + "/health")
        ok = r.status_code == 200 and r.json().get("status") == "ok"
        detail = f"GET {base}/health -> {r.status_code}"
    except Exception as e:
        ok, detail = False, f"GET {base}/health failed: {type(e).__name__}: {e}"
    if not ok:
        return Result("FAIL", "tunnel", detail,
                      "start the app (`make run`, port 8000) and the tunnel (`cloudflared tunnel run <name>`)")
    return Result("PASS", "tunnel", f"{base}/health ok")


def twilio_client(env: dict):
    from twilio.rest import Client
    return Client(env["TWILIO_ACCOUNT_SID"], env["TWILIO_AUTH_TOKEN"])


def check_webhook(env: dict) -> Result:
    need = missing(env, TWILIO_VARS + ("PUBLIC_BASE_URL",))
    if need:
        return Result("FAIL", "webhook", f"not set: {', '.join(need)}", f"fill {', '.join(need)} in .env")
    want = env["PUBLIC_BASE_URL"].strip().rstrip("/") + "/sms/inbound"
    numbers = twilio_client(env).incoming_phone_numbers.list(phone_number=env["TWILIO_FROM"], limit=1)
    if not numbers:
        return Result("FAIL", "webhook", "TWILIO_FROM is not a phone number on this Twilio account",
                      "set TWILIO_FROM to the account's number (E.164)")
    url, method = numbers[0].sms_url or "", (numbers[0].sms_method or "").upper()
    if url != want or method != "POST":
        return Result("FAIL", "webhook", f"Twilio number's messaging webhook is {method} {url or '(empty)'}, "
                      f"expected POST {want}",
                      f"Twilio console > Phone Numbers > the TWILIO_FROM number > Messaging > "
                      f"'A message comes in': Webhook, HTTP POST, {want}")
    return Result("PASS", "webhook", f"Twilio SMS webhook = POST {want}")


def check_consent(env: dict) -> Result:
    need = missing(env, ("DEMO_PHONE", "SPARE_PHONE"))
    if need:
        return Result("FAIL", "consent", f"not set: {', '.join(need)}", f"fill {', '.join(need)} in .env (E.164)")
    from app import consent, storage
    if not hasattr(consent, "get_state"):
        return Result("FAIL", "consent", "app.consent has no get_state() yet (skeleton stub)",
                      "needs b-consent-storage, issue #18")
    storage.init()
    states = {var: consent.get_state(env[var]) for var in ("DEMO_PHONE", "SPARE_PHONE")}
    off = {var: s for var, s in states.items() if s != "active"}
    if off:
        detail = ", ".join(f"{var} {mask_phone(env[var])} is {s}" for var, s in off.items())
        return Result("FAIL", "consent", detail, "text YES from each listed phone to the Safe Signal number, "
                      "with the app and tunnel running")
    return Result("PASS", "consent", "DEMO_PHONE and SPARE_PHONE are active")


def check_sms(env: dict, consent_ok: bool, timeout_s: float = SMS_TIMEOUT_S, poll_s: float = 1.0) -> Result:
    """Send R-HELP to DEMO_PHONE via Twilio and wait for status `delivered`."""
    need = missing(env, TWILIO_VARS + ("DEMO_PHONE",))
    if need:
        return Result("FAIL", "sms", f"not set: {', '.join(need)}", f"fill {', '.join(need)} in .env")
    if not consent_ok:
        return Result("FAIL", "sms", "not sent: DEMO_PHONE is not confirmed opted in",
                      "fix the consent check first (we never text a phone that hasn't opted in)")
    from app.policy import templates
    client = twilio_client(env)
    to = mask_phone(env["DEMO_PHONE"])
    t0 = time.monotonic()
    msg = client.messages.create(to=env["DEMO_PHONE"], from_=env["TWILIO_FROM"], body=templates.get("R-HELP"))
    status = msg.status
    while time.monotonic() - t0 < timeout_s:
        status = client.messages(msg.sid).fetch().status
        if status == "delivered":
            return Result("PASS", "sms", f"R-HELP delivered to {to} in {time.monotonic() - t0:.1f}s")
        if status in ("failed", "undelivered", "canceled"):
            m = client.messages(msg.sid).fetch()
            return Result("FAIL", "sms", f"R-HELP to {to} {status} (Twilio error {m.error_code})",
                          "look the error code up at twilio.com/docs/api/errors; if the phone sent STOP, "
                          "text START from it; else demo in simulated SMS mode")
        time.sleep(poll_s)
    return Result("FAIL", "sms", f"R-HELP to {to} not delivered after {timeout_s:.0f}s (last status {status})",
                  "check the phone has signal and Twilio console > Monitor > Messaging logs; "
                  "else demo in simulated SMS mode")


# --- runner -------------------------------------------------------------------------------------

def _safe(name: str, fn, *args) -> Result:
    try:
        return fn(*args)
    except Exception as e:
        return Result("FAIL", name, f"check crashed: {type(e).__name__}: {e}", "fix the error above and rerun")


def run_checks(env: dict, send_sms: bool = True) -> list[Result]:
    results = [
        _safe("model", check_model),
        _safe("app-offline", check_app),
        _safe("cached-replay", check_replay),
        _safe("tunnel", check_tunnel, env),
        _safe("webhook", check_webhook, env),
        _safe("consent", check_consent, env),
    ]
    if send_sms:
        results.append(_safe("sms", check_sms, env, results[-1].status == "PASS"))
    else:
        results.append(Result("SKIP", "sms", "--no-sms given; no test text sent"))
    return results


def report(results: list[Result], env: dict, out=sys.stdout) -> int:
    for r in results:
        print(scrub(f"{r.status} {r.name} - {r.detail}", env), file=out)
        if r.status == "FAIL":
            print(scrub(f"  fix: {r.fix}", env), file=out)
    failed = sum(r.status == "FAIL" for r in results)
    print(f"PREFLIGHT {'FAIL' if failed else 'PASS'} ({failed} of {len(results)} checks failed)", file=out)
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    unknown = [a for a in argv if a != "--no-sms"]
    if unknown:
        print(f"usage: scripts/preflight [--no-sms]  (unknown: {' '.join(unknown)})", file=sys.stderr)
        return 2
    os.environ["HF_HUB_OFFLINE"] = "1"  # set before anything imports huggingface_hub: the app must start offline
    load_env(REPO_ROOT / ".env")
    env = dict(os.environ)
    return report(run_checks(env, send_sms="--no-sms" not in argv), env)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
