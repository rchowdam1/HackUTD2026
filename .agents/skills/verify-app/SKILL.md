---
name: verify-app
description: "Verify CallSafe end to end: launch the real FastAPI backend + Vite operator console in an isolated sandbox, drive user journeys with Playwright, the API, signed Twilio webhooks and the CLIs, and prove outcomes via SSE, SQLite and files. Use after changing backend/, console/, policy/, scenarios/demo/, eval/ or scripts/, before opening a PR, or when asked whether a feature actually works."
---

# Verify CallSafe

CallSafe is one FastAPI process (`backend/app`) plus a React/Vite operator console (`console/`). Users touch it through the console (operator), the simulated or real phone (SMS keywords), Twilio's signed webhooks, and two CLIs (`python -m eval.run`, `scripts/preflight`). This skill launches the real app, drives those paths the way a user would, and writes PASS / FAIL / BLOCKED with evidence. The recipes per feature live in [`features/`](features/README.md); start there to know what a check proves.

Everything goes through one helper, `scripts/verify.py` (stdlib + the project venv + Playwright 1.64.1). Run it from the repo root (any worktree):

```bash
make verify                                   # every feature, ~4 min
make verify ARGS="--features call-replay"     # one or more features (comma list)
make verify ARGS="--checks replay.bank-alert" # exact checks (dependencies are added)
make verify-changed BASE=origin/main          # only features touched since BASE
make verify ARGS="--negative-control"         # add the deliberately-false check (must FAIL)
make verify-lint                              # drift check, no app launch, seconds
# without make (same thing):
env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --with playwright==1.64.1 \
    python .agents/skills/verify-app/scripts/verify.py run [flags]
```

Exit codes: `0` every selected check PASS; `1` any FAIL (or isolation breach); `2` nothing failed but something was BLOCKED or nothing ran. `--allow-blocked` turns 2 into 0 (CI only; the report still says BLOCKED). A check registered with `known_gap="#<issue> ..."` (a documented product bug owned elsewhere) whose assertion fails is reported as KNOWN-GAP and does not affect the exit code; any other failure category stays FAIL, and a PASS is called out under "Known product gaps" in `report.md` so the marker gets removed.

## Launch

`verify.py run` launches for you. To drive by hand: `verify.py launch [--profile cached|asr] [--no-ui]` prints the backend URL, console URL and a throwaway operator password, and leaves the instance running until `verify.py cleanup`.

What launch does, in order:

1. Takes `.verify/lock` (non-blocking). A second concurrent run or a still-running manual instance → BLOCKED, never a shared instance.
2. Snapshots the working tree (`git ls-files -co --exclude-standard`, so uncommitted edits are included; `scenarios/H1/` excluded) into `.verify/sandbox/<run_id>/`. The app resolves `data/` and `results/` from its own file path, so the sandbox's copies are what it writes.
3. Writes a clean environment (nothing inherited but PATH/HOME/locale): random `OPERATOR_PASSWORD`, `SESSION_SECRET`, `CONSENT_SALT`; random `TWILIO_AUTH_TOKEN` (signing only, no account SID or sender); fictional `DEMO_PHONE=+15550100001`, `SPARE_PHONE=+15550100002`; `PUBLIC_BASE_URL=http://127.0.0.1:<port>`; `REPLAY_SOURCE=cached` (profile `cached`) or `asr`; `HF_HUB_OFFLINE=1`; `PYTHONPATH=<sandbox>/backend`. `.env` is never read; without Twilio account credentials real-mode sends fail closed, so no real phone is ever texted.
4. Starts `python -m uvicorn app.main:app --app-dir <sandbox>/backend --port <free port>` in its own process group. Ready = `/health` 200, which uvicorn only answers after the lifespan (`storage.init`, ASR preload) completed.
5. For UI checks: `npm ci --prefer-offline` in the sandbox console, then `node node_modules/vite/bin/vite.js --port <free> --strictPort` with `BACKEND_URL` pointing at the backend. Ready = `/` serves the "CallSafe" page.

Profiles run serially: `cached` (most features), `asr` (`asr-replay`, its own instance), `cli` (preflight, no server).

## Doctor

`verify.py doctor` (manual instance) and the runner (before the first drive and after every FAIL) check, read-only:

- each recorded pid is alive and its command line contains our sandbox path (pid-reuse safe),
- the backend's process group owns the LISTEN socket on our port (`/proc/net/tcp`),
- `/health` is ok, the app created `data/safesignal.db` inside the sandbox (proves the sandbox code is what's running),
- login with the sandbox password works and the cookie opens `/aggregates`,
- the console proxies `/health`.

Unhealthy before driving → every check in that profile is BLOCKED with the doctor detail. Unhealthy after a FAIL → one relaunch, then BLOCKED.

## Drive

Checks live in `scripts/checks.py` (`verify.py list` prints them). Each one acts on one channel and asserts on another:

- **Browser:** Playwright Chromium, headless, 1440×900. Locate by role and accessible name: `get_by_role("button", name="Run bank", exact=True)`, cards via their H2 (`card(page, "^Why this alert")`), the password by placeholder `Operator password`. Every string a check relies on is in `UI_HANDLES`.
- **Console readiness:** `open_console()` navigates, logs in through the form if needed, then posts `/demo/reset` until the banner shows `reset`. The Vite proxy holds SSE headers until the first event, so a "response" or `onopen` never signals readiness.
- **Observer:** the harness keeps its own SSE subscription on the backend (`EventTap`), independent of the browser. Waits are `ctx.wait_event(predicate, since=mark, timeout)`, never fixed sleeps, except to prove nothing arrives late.
- **API:** `httpx` with the operator cookie (`ctx.api`) or without (`ctx.anon`). Twilio webhook posts are built by `post_twilio()`, signed with Twilio's documented scheme (`twilio_signature`), independent of the app's Twilio library.
- **State:** SQLite opened read-only (`ctx.db_rows`), consent found by recomputing `HMAC-SHA256(CONSENT_SALT, "consent-phone:" + E.164)`; `GET /sms/outbox` for what the simulated phone received; files in the sandbox for CLI output.
- **CLIs:** `python -m eval.run --arms K,B --batch dev` and `python scripts/preflight_checks.py --no-sms` with cwd = sandbox and the sandbox env.

To add a check: write a `@check(id, feature, profile=..., ui=..., requires=[...])` function, document its ID under the feature's `Sub-features`, add any new UI string to `UI_HANDLES` and route to `API_ROUTES`, run `make verify-lint`, then run the check and the negative control.

## Evidence

Everything for run `<run_id>` is in `.verify/runs/<run_id>/` (`.verify/runs/latest` points at the newest) and survives cleanup:

- `report.json` (schema `verify-app/report@1`): verdict, per-check status / reason / category / assertions (expected + observed) / actions / timestamps / artifacts, doctor results, environment (commit, dirty flag, snapshot digest, python / node / playwright versions), isolation fingerprint, cleanup result, per-feature coverage, external items not verified, and `reproduce` commands for whatever did not pass.
- `report.md`: the same, for humans.
- `commands.log` (every command launched), `events-<profile>.jsonl` (every SSE event with receive time), `backend-<profile>.log`, `vite-<profile>.log`, `environment.json`.
- `screenshots/<check>--<state>.png` + `.aria.txt` (ARIA snapshot) at each proof point and on every non-PASS; `artifacts/<check>--*.json|txt` for API dumps and CLI transcripts.

Proof standards: drive the real user path (buttons, `POST /demo/run`, signed webhooks, the CLIs), never internal setters. Assert the action *and* the resulting state, including side effects (SQLite rows, outbox, files). PASS requires at least one executed assertion and all assertions true. Missing Playwright, Chromium, the whisper model or a precondition check → BLOCKED with the reason. A Playwright locator failure is FAIL category `ui-locator`: either the UI regressed or the map drifted; `make verify-lint` and the screenshot tell which. `harness-error` (an exception in the harness itself) is BLOCKED, never PASS. The run also fingerprints the checkout's `data/` and `results/` before and after; any change fails the run as an isolation breach. Before trusting a harness change, run with `--negative-control`: `control.invalid-assertion` must FAIL.

Never report items listed under `external` in `features/coverage.json` (real Twilio SMS, arm C live, H1 scoring, …) as verified from a local run.

## Cleanup

`verify.py run` cleans up in a `finally`: it kills only the process groups it started (pid + sandbox path in cmdline, SIGTERM then SIGKILL), deletes `.verify/sandbox/<run_id>/` (refuses any path outside `.verify/sandbox/`), removes `.verify/state.json`, and then checks that every artifact in the report still exists. `--keep-sandbox` keeps the sandbox for debugging. For a manual instance or a crashed run: `verify.py cleanup` (stops the recorded instance, removes orphaned sandboxes, keeps `.verify/runs/`). Never kill by process name: other uvicorn/vite processes on this machine are not ours. Delete old evidence by hand when you no longer need it (`rm -rf .verify/runs/<run_id>`).

## Helpers

All under `scripts/`, invoked as `verify.py <command>` (see top of this file for the full prefix):

| Command | Does |
|---|---|
| `run [--features a,b] [--checks id,..] [--changed BASE] [--negative-control] [--allow-blocked] [--keep-sandbox]` | launch → doctor → drive → evidence → cleanup |
| `launch [--profile cached\|asr] [--no-ui]` / `doctor` / `cleanup` / `status` | manual instance lifecycle |
| `list` | checks by feature, profile, UI/API, dependencies |
| `affected [--base REF] [--json]` | changed files → features (what `--changed` runs), unmapped files |
| `lint` | drift between docs, `coverage.json`, checks, UI strings in `console/src`, routes in `backend/app`, and per-feature sync commits |
| `sync [--report PATH] [--features a,b]` | after a clean-tree run at HEAD, record HEAD as each verified feature's `synced_commit` |

Modules: `harness.py` (lock, sandbox, launch, doctor, cleanup, isolation fingerprint), `context.py` (SSE observer, SQLite read-back, Playwright, assertion recorder), `checks.py` (journeys), `maint.py` (affected / lint / sync), `verify.py` (CLI + reports).

Keeping this skill true as the app changes is the `maintain-verification` skill (`.agents/skills/maintain-verification/SKILL.md`). The pipeline's ordering guarantees (stale sends, one follow-up) are model-checked separately by `verify-pipeline-formal`.

Human-facing overview (prerequisites, statuses, CI, troubleshooting): `docs/verification.md`. Keep it in step when this skill changes.
