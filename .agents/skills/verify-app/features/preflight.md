# Preflight

`scripts/preflight` is the team's go/no-go before each judging block: whisper loads offline, the app starts offline with the demo routes, cached replays produce the expected decisions, then tunnel, Twilio webhook, phone consent, power and a real SMS round trip. It prints `PASS|FAIL|SKIP <name> - <detail>` per check and exits 1 if anything failed, never printing secrets or full numbers.

## Sub-features

- `preflight.offline-checks` runs `scripts/preflight_checks.py --no-sms` in the sandbox: `app-offline` and `cached-replay` PASS, `sms` SKIP, overall FAIL without live infrastructure, and no secret or raw number in the output.
- `preflight.model` expects the `model` line to PASS when whisper is cached (BLOCKED otherwise).

## How to get to it (user POV)

- `make preflight` or `scripts/preflight [--no-sms]` on the demo laptop.

## Driving it with verify.py

Preconditions:

- Profile `cli` (no server). The harness calls `python scripts/preflight_checks.py --no-sms` directly with the sandbox env and no `PUBLIC_BASE_URL`; the `scripts/preflight` wrapper would `uv run` inside the sandbox and build a second venv.

- **Run.** One invocation, shared by both checks. Output saved to `artifacts/preflight-stdout.txt` with the exit code.
- **Offline checks.** Lines `PASS app-offline`, `PASS cached-replay`, `SKIP sms`; exit 1 with `PREFLIGHT FAIL` (tunnel, webhook, consent fail without live infrastructure, which is the correct answer here).
- **No leaks.** None of the sandbox secrets and not the raw `DEMO_PHONE` appear in stdout.
- **Model.** Line `PASS model` when the cache exists.

## Gotchas

- The live half (tunnel, webhook, consent, SMS round trip, AC power) is external; a FAIL there in the sandbox is expected and not a product bug.
- Preflight reads `.env` from the repo root it runs in; the sandbox has none, by design.
- `check_replay` patches the SMS gateway, so preflight never texts anyone even when Twilio is configured.
