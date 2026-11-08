---
name: verify-app
description: "Verify CallSafe end to end: launch the real backend + console in an isolated sandbox, drive user journeys (Playwright, API, signed Twilio webhooks, CLIs), and prove outcomes via SSE, SQLite and files. Use after changing backend/, console/, policy/, scenarios/demo/, eval/ or scripts/, before a PR, or when asked whether a feature works."
---

# Verify CallSafe

Each check drives a real user path (buttons, `POST /demo/run`, signed Twilio webhooks, the CLIs) and then confirms the result on a separate channel (SSE events, SQLite read-only, `GET /sms/outbox`, files). The recipe for each feature is in [`features/`](features/README.md). `features/coverage.json` maps source paths to features.

```bash
make verify-changed BASE=origin/main          # features touched since BASE
make verify ARGS="--features call-replay"     # some features
make verify ARGS="--checks replay.bank-alert" # exact checks
make verify ARGS="--negative-control"         # control.invalid-assertion must FAIL
make verify-lint                              # drift between docs, checks, UI strings, routes
```

Exit codes: 0 = all PASS, 1 = a FAIL or isolation breach, 2 = BLOCKED or nothing ran. `--allow-blocked` turns 2 into 0 and is for CI only.

## Rules

- PASS needs at least one assertion to run and every assertion to hold. A missing tool, model or precondition, or an exception in the harness, is BLOCKED, never PASS.
- Assert the user action and its side effects (SQLite rows, outbox, files). Never call internal setters.
- Wait on events with `ctx.wait_event(...)`, never fixed sleeps. The one exception is proving that nothing arrives late.
- Never weaken an assertion or delete a check to get green. A product bug stays FAIL until its owner tracks it in an issue. Only then may the check be marked `known_gap="#<issue> ..."`, which reports KNOWN-GAP.
- Never report the items in `coverage.json` → `external` (real Twilio SMS, arm C live, H1 scoring) as verified.
- Never kill processes by name. Other uvicorn and vite processes on the machine aren't ours.

## Adding a check

1. Write a `@check(id, feature, profile=..., ui=..., requires=[...])` function in `scripts/checks.py`.
2. List its ID under the feature doc's `Sub-features`. Add any new UI string to `UI_HANDLES` and any new route to `API_ROUTES`.
3. Run `make verify-lint`, then run the check together with `--negative-control`.

Browser locators use roles and accessible names (`get_by_role("button", name="Run bank", exact=True)`), find cards by their H2, and find the password field by its placeholder `Operator password`.

## Helpers

`scripts/verify.py <command>`. Prefix: `env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --with playwright==1.64.1 python .agents/skills/verify-app/scripts/verify.py`.

| Command | Does |
|---|---|
| `run [--features] [--checks] [--changed BASE] [--negative-control] [--allow-blocked] [--keep-sandbox]` | launch, doctor, drive, write evidence, clean up |
| `launch [--profile cached\|asr] [--no-ui]` / `doctor` / `cleanup` / `status` | run an instance by hand |
| `list` | list checks |
| `affected [--base REF] [--json]` | map changed files to features |
| `lint` | detect drift |
| `sync` | after a clean-tree PASS at HEAD, record HEAD as each feature's `synced_commit` |

Modules: `harness.py` (sandbox, launch, doctor, cleanup), `context.py` (SSE observer, SQLite, Playwright, assertions), `checks.py`, `maint.py` (affected/lint/sync), `verify.py` (CLI and reports).

Evidence is in `.verify/runs/<run_id>/`: `report.{json,md}`, `screenshots/`, `events-*.jsonl`, backend and vite logs, and `artifacts/`.
