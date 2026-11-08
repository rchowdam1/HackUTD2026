"""`make demo`: bring the whole demo up on one laptop and print what the presenter needs.

Order: .env key table -> Twilio CLI installed -> warm whisper -> ports -> cloudflared tunnel -> backend
(REPLAY_SOURCE=asr) + console -> Twilio number webhooks (Twilio CLI) -> preflight --no-sms -> summary.
Flags: --no-twilio (mic + replay only, simulated SMS), --tailnet (tailscale serve the console).
If the tunnel drops it starts a new one and re-points the number. Ctrl-C stops every child it started.
Never prints secrets, DEMO_PHONE or SPARE_PHONE.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

import demo_up
import httpx
from preflight_checks import REPO_ROOT, load_env, missing, scrub

ENV_FILE = REPO_ROOT / ".env"
KEYS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "DEMO_PHONE", "SPARE_PHONE", "OPERATOR_PASSWORD",
        "SESSION_SECRET", "CONSENT_SALT", "OPENROUTER_API_KEY", "INTENT_MODEL", "PUBLIC_BASE_URL", "CLOUDFLARED_TUNNEL")
REQUIRED = ("OPERATOR_PASSWORD", "SESSION_SECRET", "CONSENT_SALT")
TWILIO_REQUIRED = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM", "DEMO_PHONE")
STOP_TIMEOUT_S = 10


def say(msg: str) -> None:
    print(f"demo: {msg}", flush=True)


def key_table(env: dict) -> str:
    return "\n".join(f"  {k:<20} {'set' if (env.get(k) or '').strip() else 'EMPTY'}" for k in KEYS)


def check_keys(env: dict, twilio: bool) -> None:
    need = missing(env, REQUIRED + (TWILIO_REQUIRED if twilio else ()))
    if need:
        hint = "" if not twilio else " (or run `make demo ARGS=--no-twilio` for mic + replay only)"
        sys.exit(f"demo: fill {', '.join(need)} in .env{hint}")


def arm_c() -> bool:
    return os.environ.get("INTENT_MODEL", "").strip().lower() == "on" and bool(
        os.environ.get("OPENROUTER_API_KEY", "").strip())


def port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def pick_port(preferred: int, fallback_from: int) -> int:
    if port_free(preferred):
        return preferred
    return next(p for p in range(fallback_from, fallback_from + 100) if port_free(p))


def format_us(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    if len(digits) == 11 and digits[0] == "1":
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return number


def twilio(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["twilio", *args], capture_output=True, text=True)


def require_twilio_cli() -> None:
    if shutil.which("twilio") is None:
        sys.exit("demo: the Twilio CLI is not installed (brew install twilio/brew/twilio), "
                 "or run `make demo ARGS=--no-twilio`")


def webhook_urls(base: str) -> dict[str, str]:
    return {"smsUrl": f"{base}/sms/inbound", "voiceUrl": f"{base}/voice/incoming"}


def webhook_argv(number: str, base: str) -> list[str]:
    return ["twilio", "phone-numbers:update", number, f"--voice-url={base}/voice/incoming", "--voice-method=POST",
            f"--sms-url={base}/sms/inbound", "--sms-method=POST"]


def point_webhooks(number: str, base: str) -> None:
    env = dict(os.environ)
    done = subprocess.run(webhook_argv(number, base), capture_output=True, text=True)
    if done.returncode != 0:
        sys.exit(scrub(f"demo: twilio phone-numbers:update failed: {done.stderr.strip()[-400:]}", env))
    listed = twilio("phone-numbers:list", "-o", "json")
    rows = json.loads(listed.stdout or "[]") if listed.returncode == 0 else []
    row = next((r for r in rows if r.get("phoneNumber") == number), {})
    want = webhook_urls(base)
    wrong = [k for k, v in want.items() if row.get(k) != v]
    if wrong:
        sys.exit(f"demo: the number's {', '.join(wrong)} did not take (read back from `twilio phone-numbers:list`)")
    say("Twilio webhooks (read back ok): " + ", ".join(f"{k} POST {v}" for k, v in want.items()))


def public_ip(host: str) -> str | None:
    """The host's A record from public DNS (Cloudflare DoH), which is what Twilio sees."""
    r = httpx.get("https://cloudflare-dns.com/dns-query", params={"name": host, "type": "A"},
                  headers={"accept": "application/dns-json"}, timeout=5)
    return next((a["data"] for a in r.json().get("Answer", []) if a.get("type") == 1), None)


def tunnel_answers(base: str, timeout_s: float = 60) -> bool:
    # A fresh quick tunnel's hostname takes a few seconds to exist. Asking the laptop's resolver too early
    # caches "not found" (seen with Tailscale's MagicDNS), so resolve through public DNS and connect by IP.
    host = base.removeprefix("https://").split("/")[0]
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if ip := public_ip(host):
                with httpx.Client(timeout=5) as c:
                    r = c.get(f"https://{ip}/health", headers={"Host": host}, extensions={"sni_hostname": host})
                if r.status_code == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def spawn(cmd: list[str], **kw) -> subprocess.Popen:
    # Own process group, so stopping it also stops grandchildren (npx -> vite, uvicorn workers).
    return subprocess.Popen(cmd, start_new_session=True, **kw)


def stop(procs: list[subprocess.Popen]) -> None:
    for p in reversed(procs):
        if p.poll() is None:
            send(p, signal.SIGTERM)
    deadline = time.monotonic() + STOP_TIMEOUT_S
    for p in procs:
        try:
            p.wait(timeout=max(deadline - time.monotonic(), 0.1))
        except subprocess.TimeoutExpired:
            send(p, signal.SIGKILL)


def send(p: subprocess.Popen, sig: int) -> None:
    try:
        if os.getpgid(p.pid) == p.pid:
            os.killpg(p.pid, sig)
        else:
            p.send_signal(sig)
    except ProcessLookupError:
        pass


def interrupt(signum, frame):
    raise KeyboardInterrupt


def tailnet_up(console_port: int) -> str:
    subprocess.run(["tailscale", "serve", "--bg", str(console_port)], check=True, capture_output=True)
    status = subprocess.run(["tailscale", "serve", "status"], capture_output=True, text=True).stdout
    m = re.search(r"https://\S+", status)
    return m.group(0) if m else "(see `tailscale serve status`)"


def main(argv: list[str]) -> int:
    unknown = [a for a in argv if a not in ("--no-twilio", "--tailnet")]
    if unknown:
        print(f"usage: scripts/demo [--no-twilio] [--tailnet]  (unknown: {' '.join(unknown)})", file=sys.stderr)
        return 2
    use_twilio, tailnet = "--no-twilio" not in argv, "--tailnet" in argv
    # Children run in their own sessions, so a closed terminal (SIGHUP) or kill (SIGTERM) must reach them
    # through our cleanup; SIGINT is reset because a shell's `cmd &` starts us with it ignored.
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupt)

    load_env(ENV_FILE)
    print("demo: .env keys\n" + key_table(dict(os.environ)), flush=True)
    check_keys(dict(os.environ), use_twilio)
    if os.environ.get("OPENROUTER_API_KEY", "").strip() and not os.environ.get("INTENT_MODEL", "").strip():
        os.environ["INTENT_MODEL"] = "on"
        say("OPENROUTER_API_KEY is set and INTENT_MODEL is empty: running with INTENT_MODEL=on (arm C)")
    if arm_c():
        say("notice: arm C sends each caller turn (and the turns before it) to OpenRouter")

    if use_twilio:
        # No named CLI profile: the CLI gives TWILIO_ACCOUNT_SID/AUTH_TOKEN from .env (inherited) priority over
        # any profile, which is the account the app sends from and that owns TWILIO_FROM.
        require_twilio_cli()

    say("warming faster-whisper small.en (downloads once)")
    subprocess.run([sys.executable, "-c", "from app import asr; asr.load_model()"], check=True, cwd=REPO_ROOT)
    os.environ["REPLAY_SOURCE"] = "asr"  # the backend preloads whisper at startup

    port = pick_port(int(os.environ.get("DEMO_PORT") or 8000), 8010)
    console_port = pick_port(int(os.environ.get("CONSOLE_PORT") or 5173), 5180)
    for name, got, want in (("backend", port, os.environ.get("DEMO_PORT") or "8000"),
                            ("console", console_port, os.environ.get("CONSOLE_PORT") or "5173")):
        if str(got) != want:
            say(f"port {want} is busy: {name} on {got}")

    procs: list[subprocess.Popen] = []
    tailnet_on = False
    try:
        base = None
        if use_twilio:
            demo_up.PORT = port  # start_tunnel reads it at call time
            tunnel, base = demo_up.start_tunnel()
            procs.append(tunnel)
            os.environ["PUBLIC_BASE_URL"] = base  # beats .env: uvicorn's --env-file never overrides set vars
            say(f"tunnel {base} -> 127.0.0.1:{port} (Twilio webhooks and /health only)")
        procs.append(backend(port))
        console = REPO_ROOT / "console"
        if not (console / "node_modules").is_dir():
            say("console: npm ci")
            subprocess.run(["npm", "ci"], cwd=console, check=True)
        console_env = {**os.environ, "BACKEND_URL": f"http://127.0.0.1:{port}"}
        if tailnet:
            console_env["__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS"] = ".ts.net"  # vite rejects unknown Host headers
        procs.append(spawn(["npx", "vite", "--port", str(console_port), "--strictPort"], cwd=console,
                           env=console_env))
        if not demo_up.wait_healthy(procs[-2], f"http://127.0.0.1:{port}/health"):
            say("backend did not become healthy; stopping")
            return 1
        say(f"backend on http://127.0.0.1:{port}")

        if base:
            expose(base)

        say("preflight --no-sms (real SMS is carrier-blocked: Twilio 30034)")
        verdict = subprocess.run([str(REPO_ROOT / "scripts" / "preflight"), "--no-sms"], cwd=REPO_ROOT).returncode
        expected = "" if use_twilio else "; tunnel, webhook and consent FAIL by design with --no-twilio"
        say("preflight: GO" if verdict == 0
            else f"preflight: NO-GO (see FAIL lines above; the stack stays up{expected})")

        tailnet_url = None
        if tailnet:
            tailnet_url = tailnet_up(console_port)
            tailnet_on = True
        print(summary(console_port, tailnet_url, use_twilio), flush=True)
        while True:
            time.sleep(1)
            if base and procs[0].poll() is not None:
                procs[0], procs[1], base = recover_tunnel(port, procs[1], base)
            if any(p.poll() is not None for p in procs):
                say("a child process exited; stopping the rest")
                return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)  # a second Ctrl-C must not cut cleanup short
        if tailnet_on:
            subprocess.run(["tailscale", "serve", "--https=443", "off"], capture_output=True)
        stop(procs)


def backend(port: int) -> subprocess.Popen:
    return spawn(["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port),
                  *(["--env-file", str(ENV_FILE)] if ENV_FILE.exists() else [])], cwd=REPO_ROOT)


def expose(base: str) -> None:
    # Point the number only at a tunnel that answers, never at a dead URL.
    if tunnel_answers(base):
        say(f"tunnel ok: {base}/health")
        point_webhooks(os.environ["TWILIO_FROM"], base)
    else:
        say(f"WARN tunnel: {base}/health did not answer within 60 s; webhooks left unchanged, calls will not reach "
            "the app (use Start live conversation or a replay)")


def recover_tunnel(port: int, app: subprocess.Popen, base: str) -> tuple[subprocess.Popen, subprocess.Popen, str]:
    """A dropped tunnel ends the call in progress; bring up a new one so the next call works without a restart."""
    say("tunnel exited; starting a new one")
    tunnel, new_base = demo_up.start_tunnel()
    os.environ["PUBLIC_BASE_URL"] = new_base
    if new_base != base:
        # A quick tunnel gets a new hostname, and the backend signs and checks Twilio webhooks against it.
        say("new tunnel hostname: restarting the backend (the console reconnects by itself)")
        stop([app])
        app = backend(port)
        if not demo_up.wait_healthy(app, f"http://127.0.0.1:{port}/health"):
            say("backend did not come back after the tunnel restart")
    expose(new_base)
    return tunnel, app, new_base


def summary(console_port: int, tailnet_url: str | None, use_twilio: bool) -> str:
    lines = ["", "=" * 60, f"  Console:  http://127.0.0.1:{console_port}"]
    if tailnet_url:
        lines.append(f"  Tailnet:  {tailnet_url}")
    if use_twilio:
        lines.append(f"  Call {format_us(os.environ['TWILIO_FROM'])} to start a live call")
        lines.append("  Real SMS: carrier-blocked until 10DLC registration (Twilio 30034) "
                     "— console phone frame mirrors every send")
    else:
        lines.append("  --no-twilio: no tunnel, no live calls; SMS is simulated in the console phone frame")
    lines.append(f"  Arm:      {'C (rules + AI)' if arm_c() else 'B (rules only)'}")
    lines.append("  Fallbacks: Start live conversation (laptop mic); Run grandson replay")
    lines.append("  Ctrl-C stops everything.")
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
