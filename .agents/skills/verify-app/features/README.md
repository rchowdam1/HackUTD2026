# Safe Signal verification map

This directory is the maintained source for verifying what Safe Signal's users can do: the operator at the judging table (console), the subscriber's phone (SMS replies), Twilio (webhooks), and the team's CLIs (eval, preflight). Read this index before driving the app, then use the matching feature file as the recipe. `coverage.json` is the machine-readable half: which source paths each feature covers, which paths force a full run, what is out of automated scope, and the commit each feature was last verified at.

## Baseline preconditions

- Run everything through `make verify*` (or the `uv run --with playwright==1.64.1 ... verify.py` line in `../SKILL.md`). It launches its own instance; never drive an instance you did not launch.
- Each run snapshots the working tree into `.verify/sandbox/<run_id>/` (minus `scenarios/H1/`), so the app's `data/safesignal.db` and `results/` are the sandbox's, not the checkout's.
- The sandbox environment is generated: random `OPERATOR_PASSWORD`, `SESSION_SECRET`, `CONSENT_SALT`, a signing-only `TWILIO_AUTH_TOKEN`, `DEMO_PHONE=+15550100001`, `SPARE_PHONE=+15550100002`, `REPLAY_SOURCE=cached` (profile `cached`) or `asr` (profile `asr`), `HF_HUB_OFFLINE=1`. `.env` is never read. There is no `TWILIO_ACCOUNT_SID`, so real-mode sends fail closed.
- A fresh sandbox has no consent row (state `invited`) and no reply counts. Checks that need an opted-in phone reply YES first.
- `results/latest.json` is committed (H1 numbers). `results.pending` moves the sandbox copy aside; `results.eval-cli-to-card` regenerates it from the dev batch.

## Driving conventions

- Start every recipe from the baseline. Checks that change shared state (consent, SMS mode) restore it before they end.
- Prefer roles and accessible names: buttons by exact name (`Run bank`, `WRONG`), cards (`.card`, a `<section>` or, for the WRONG counter, a `<div>`) by their H2 (`Live transcript`, `Why this alert`, `Phone`, `WRONG replies`, `Held-out results`, `Where we fail`). The password input has no label; use its placeholder `Operator password`.
- Every UI string a check depends on is listed in `UI_HANDLES` in `../scripts/checks.py`; `verify.py lint` fails when one disappears from `console/src`.
- Wait on events, never on sleeps: the harness's own SSE subscriber (`events-<profile>.jsonl`) is the clock. The only fixed waits are "wait past the replay's natural end" to prove that nothing late arrives.
- Replays are real time: clinic ≈14 s, bank ≈22 s. A full run takes about 4 minutes.

## Proof and skip reporting

- Every UI assertion is paired with an independent read: the SSE event stream, SQLite (`data/safesignal.db` opened read-only), `GET /sms/outbox`, `GET /aggregates`, or a file on disk.
- Consent rows are found by recomputing `sha256(CONSENT_SALT + E.164)`, not by asking the app.
- Each check records its actions, assertions (expected / observed), timestamps, and artifacts (screenshot + ARIA snapshot, JSON dumps, CLI transcripts) in `.verify/runs/<run_id>/`.
- Outcomes are PASS, FAIL, or BLOCKED with a reason and category. A check with zero executed assertions is BLOCKED. A missing dependency is BLOCKED. Neither is ever a pass.
- Items listed under `external` in `coverage.json` are reported as unverified in every report; do not claim them from a local run.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections, in this order (`verify.py lint` enforces it):

1. `Sub-features` lists the check IDs, one line each. Every check in `checks.py` for the feature must appear here and vice versa.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with verify.py` starts with `Preconditions:` and uses labeled bullets that pair each user action with the exact handle or command and the observable result.
4. `Gotchas` lists traps that waste or invalidate a run.

## Features

- [Operator login](./operator-login.md) covers the password form, the signed session cookie, and the 401 wall on every operator route.
- [Call replay](./call-replay.md) covers Run clinic (silent, "not a safety verdict") and Run bank (alert, Why panel, auto end-call, one follow-up).
- [SMS replies](./sms-replies.md) covers the simulated phone's YES / WRONG / SHARED / STOP buttons, keyword normalisation, the WRONG counter, and consent gating of alerts.
- [Call controls](./call-controls.md) covers End call and Reset mid-replay and the real / simulated SMS-mode toggle.
- [Results card](./results-card.md) covers the pending state and `python -m eval.run` feeding the results and "Where we fail" cards.
- [Twilio webhooks](./twilio-webhooks.md) covers signature enforcement, inbound replies with MessageSid dedupe, and status callbacks.
- [Enrollment invite](./enrollment-invite.md) covers `POST /sms/invite` for the demo and spare phones and hashed-only storage.
- [Fixture replay](./fixture-replay.md) covers the console's backend-free `?fixtures` mode.
- [ASR replay](./asr-replay.md) covers whisper transcription of the demo audio when `REPLAY_SOURCE=asr`.
- [Preflight](./preflight.md) covers the offline parts of `scripts/preflight`.
