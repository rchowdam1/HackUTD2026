# CallSafe verification map

This directory is the maintained source for verifying what CallSafe's users can do: the operator at the judging table (console), the subscriber's phone (SMS replies), Twilio (webhooks), and the team's CLIs (eval, preflight). Read this index before driving the app, then use the matching feature file as the recipe. `coverage.json` is the machine-readable half: which source paths each feature covers, which paths force a full run, what is out of automated scope, and the commit each feature was last verified at.

## Baseline preconditions

- Run everything through `make verify*` (or the `uv run --with playwright==1.64.1 ... verify.py` line in `../SKILL.md`). It launches its own instance; never drive an instance you did not launch.
- Each run snapshots the working tree into `.verify/sandbox/<run_id>/` (minus `scenarios/H1/`), so the app's `data/safesignal.db` and `results/` are the sandbox's, not the checkout's.
- The sandbox environment is generated: random `OPERATOR_PASSWORD`, `SESSION_SECRET`, `CONSENT_SALT`, a random `TWILIO_AUTH_TOKEN` (signing only), `PUBLIC_BASE_URL=http://127.0.0.1:<port>`, `DEMO_PHONE=+15550100001`, `SPARE_PHONE=+15550100002`, `REPLAY_SOURCE=cached` (profile `cached`) or `asr` (profile `asr`), `HF_HUB_OFFLINE=1`. `.env` is never read. There is no `TWILIO_ACCOUNT_SID`/`TWILIO_FROM`, so real-mode sends fail closed.
- A fresh sandbox has no consent row (state `invited`) and no reply counts. Checks that need an opted-in phone reply YES first.
- `results/latest.json` is committed (H1 numbers). `results.pending` moves the sandbox copy aside; `results.eval-cli-to-api` regenerates it from the dev batch.

## Driving conventions

- Start every recipe from the baseline. Checks that change shared state (consent, SMS mode) restore it before they end.
- Prefer roles and accessible names: buttons by exact name (`Run bank`, `WRONG`), cards (`.card` `<section>`s) by their H2 (`Live transcript`, `Why this alert`, `Phone`). The password input has no label; use its placeholder `Operator password`.
- Every UI string a check depends on is listed in `UI_HANDLES` in `../scripts/checks.py`; `verify.py lint` fails when one disappears from `console/src`.
- Wait on events, never on sleeps: the harness's own SSE subscriber (`events-<profile>.jsonl`) is the clock. The only fixed waits are "wait past the replay's natural end" to prove that nothing late arrives.
- Cached replays are paced by their turn audio (each line is due at its `t_start_ms`): clinic ≈15 s, bank ≈22 s, grandson ≈29 s.

## Proof and skip reporting

- Every UI assertion is paired with an independent read: the SSE event stream, SQLite (`data/safesignal.db` opened read-only), `GET /sms/outbox`, `GET /aggregates`, or a file on disk.
- Consent rows are found by recomputing `HMAC-SHA256(CONSENT_SALT, "consent-phone:" + E.164)`, not by asking the app.
- Each check records its actions, assertions (expected / observed), timestamps, and artifacts (screenshot + ARIA snapshot, JSON dumps, CLI transcripts) in `.verify/runs/<run_id>/`.
- Outcomes are PASS, FAIL, or BLOCKED with a reason and category, plus KNOWN-GAP for an app-behavior FAIL of a check marked `known_gap` (a documented, issue-tracked product bug; it does not fail the run). A check with zero executed assertions is BLOCKED. A missing dependency is BLOCKED. Neither is ever a pass.
- Items listed under `external` in `coverage.json` are reported as unverified in every report; do not claim them from a local run.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections, in this order (`verify.py lint` enforces it):

1. `Sub-features` lists the check IDs, one line each. Every check in `checks.py` for the feature must appear here and vice versa.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with verify.py` starts with `Preconditions:` and uses labeled bullets that pair each user action with the exact handle or command and the observable result.
4. `Gotchas` lists traps that waste or invalidate a run.

## Features

- [Operator login](./operator-login.md) covers the password form, the signed server-side session cookie, and the 401 wall on every operator route.
- [Call replay](./call-replay.md) covers Run clinic (silent, "No alert detected"), Run bank (alert, Why panel, auto end-call, one follow-up) and Run grandson (rules alone stay silent; the model catches it).
- [SMS replies](./sms-replies.md) covers the simulated phone's YES / WRONG / SHARED / STOP buttons, keyword normalisation, WRONG counting, and consent gating of alerts.
- [Call controls](./call-controls.md) covers End call and Reset mid-replay and the real / simulated SMS-mode toggle.
- [Results card](./results-card.md) covers `GET /results/latest` (pending, and `python -m eval.run` output served byte-for-byte); the console no longer shows results.
- [Twilio webhooks](./twilio-webhooks.md) covers `X-Twilio-Signature` on `/sms/inbound` and `/sms/status`, sender binding, MessageSid dedupe and status callbacks.
- [Live call](./live-call.md) covers the Twilio voice webhook TwiML, signature checks on `/voice/incoming` and the `/voice/stream` socket, and a signed synthetic Media Stream of the bank call transcribed live.
- [Enrollment invite](./enrollment-invite.md) covers `POST /sms/invite` for the demo and spare phones and hashed-only storage.
- [Fixture replay](./fixture-replay.md) covers the console's backend-free `?fixtures` mode.
- [Live mic](./live-mic.md) covers the console's browser-mic conversation: Start, Caller / You turns, alert mid-call, follow-up on End call.
- [Hard stop](./hard-stop.md) covers the demo hold: on an alert the caller is held, a spoken warning plays, and the operator returns to the call or hangs up.
- [Console design](./console-design.md) covers the DESIGN.md layout at 1440x900 and 1920x1080 (no page scroll, magenta only where allowed, the results band from `results/latest.json`) and the per-turn ticker, including reduced motion.
- [ASR replay](./asr-replay.md) covers whisper transcription of the demo audio when `REPLAY_SOURCE=asr`.
- [Preflight](./preflight.md) covers the offline parts of `scripts/preflight`.
