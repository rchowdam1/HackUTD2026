"""H+1 real-SMS kill check (PRD §19.7, #29): N outbound texts to DEMO_PHONE, then one inbound reply.

Sends the real ALERT-OTP-01 text (so segment counts match the demo), polls each message to a final
status, and prints median/worst delivery time, segment counts, and whether an inbound reply arrived.
Run with the app stopped, or its webhook answers the reply with R-HELP (harmless). Prints no numbers.
Usage: uv run python scripts/sms_kill_check.py [N]
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from datetime import datetime, timezone

from preflight_checks import REPO_ROOT, TWILIO_VARS, load_env, missing

FINAL = {"delivered", "undelivered", "failed"}
TIMEOUT_S = 120
TRIAL_PREFIX = "Sent from your Twilio trial account"


def wait_final(client, sid: str, t0: float) -> tuple[str, float, int]:
    while True:
        m = client.messages(sid).fetch()
        if m.status in FINAL or time.monotonic() - t0 > TIMEOUT_S:
            return m.status, time.monotonic() - t0, int(m.num_segments or 0)
        time.sleep(0.5)


def summary(results: list[tuple[str, float, int]]) -> str:
    times = [t for s, t, _ in results if s == "delivered"]
    segs = sorted({n for _, _, n in results})
    if not times:
        return f"0/{len(results)} delivered; segments {segs}"
    return (f"{len(times)}/{len(results)} delivered; median {statistics.median(times):.1f} s, "
            f"worst {max(times):.1f} s; segments {segs}")


def main(argv: list[str]) -> int:
    load_env(REPO_ROOT / ".env")
    need = missing(dict(os.environ), TWILIO_VARS + ("DEMO_PHONE",))
    if need:
        print(f"not set: {', '.join(need)} (fill them in .env)")
        return 2
    n = int(argv[0]) if argv else 10
    from twilio.rest import Client

    from app.policy import templates
    client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    if client.api.accounts(os.environ["TWILIO_ACCOUNT_SID"]).fetch().type == "Trial":
        print(f"WARN trial account: texts get the '{TRIAL_PREFIX}' prefix (§19.5); upgrade before the demo")
    body, to, from_ = templates.get("ALERT-OTP-01"), os.environ["DEMO_PHONE"], os.environ["TWILIO_FROM"]

    results = []
    for i in range(n):
        t0 = time.monotonic()
        sid = client.messages.create(to=to, from_=from_, body=body).sid
        results.append(wait_final(client, sid, t0))
        print(f"  {i + 1}/{n}: {results[-1][0]} in {results[-1][1]:.1f} s, {results[-1][2]} segment(s)")

    since = datetime.now(timezone.utc)
    print("Now reply WRONG from the demo phone (waiting up to 120 s)...")
    t0, inbound = time.monotonic(), None
    while inbound is None and time.monotonic() - t0 < TIMEOUT_S:
        time.sleep(2)
        inbound = next(iter(client.messages.list(from_=to, to=from_, date_sent_after=since, limit=1)), None)
    got = f"inbound reply seen after {time.monotonic() - t0:.0f} s" if inbound else "NO inbound reply in 120 s"

    line = f"{summary(results)}; {got}"
    print(f"\nRESULT {line}")
    print(f"Post on the board: LEARN H+1 Twilio kill check ({n} texts, ALERT-OTP-01 body): {line}")
    ok = inbound is not None and all(s == "delivered" for s, _, _ in results)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
