# Verification

The verification system launches the real app in a sandbox, uses it the way the operator, the phone and Twilio do, and reports PASS, FAIL or BLOCKED with evidence for each check. Agents should read the skills in `.agents/skills/`. They are the source of truth, and `make verify-lint` keeps them in step with the code.

```bash
make verify-changed                               # features touched since origin/main (before a PR)
make verify                                       # all features, ~4 min
make verify ARGS="--checks replay.bank-alert"     # one check (its dependencies are added)
make verify ARGS="--negative-control"             # adds a check that must FAIL
make verify-lint                                  # docs/map/UI/route drift, seconds
make verify-formal                                # TLA+ model check of pipeline.py, ~5 s
```

Results go to `.verify/runs/latest/report.md`, with screenshots, the event log and app logs next to it. Exit codes: 0 = all PASS, 1 = a FAIL, 2 = BLOCKED or nothing ran.

## Prerequisites

- `uv` and Python 3.11 (`make install`).
- For console checks: Node 20.19+ and Chromium for Playwright 1.64.1 (`env -u PYTHONPATH -u VIRTUAL_ENV uv run --with playwright==1.64.1 playwright install chromium`).
- For `asr-replay` and `preflight.model`: faster-whisper `small.en` in `~/.cache/huggingface`.
- For `make verify-formal`: Java 11+ and GNU grep (Linux).

If one of these is missing, the checks that need it come back BLOCKED. BLOCKED is never a pass.

## Safety

Each run copies the working tree, minus `scenarios/H1/`, into `.verify/sandbox/<run_id>/`. It never reads `.env`, uses random secrets and made-up phone numbers, and has no Twilio account SID or sender, so it never texts anyone. It never uses ports 8000 or 5173, and only one run happens at a time. Cleanup kills only the processes the run started, and the run FAILs if your `data/` or `results/` changed.

## Not covered by automation

Real Twilio SMS to a phone, Twilio webhooks through the cloudflared tunnel, `scripts/demo_up`, Twilio's own STOP handling, arm C in a live call, H1 scoring, voice generation and the physical demo setup. Check those by hand with `scripts/preflight` and `docs/twilio-live.md`.

## Open finding

PRD §19.10 says a reset call "never sends SMS". The formal model shows the code can't promise that: if Reset lands after the worker thread's live check, the alert still goes out. Details are in `.agents/skills/verify-pipeline-formal/SKILL.md`.

## CI

`.github/workflows/verify.yml` runs `make verify-lint` and `make verify-changed --allow-blocked` on PRs that touch app or verification paths. Docs-only PRs don't trigger it. FAIL fails the job, and the evidence is uploaded as the `verify-evidence` artifact.

## Troubleshooting

- `another verification run holds .verify/lock`: wait for that run to finish. `verify.py status` shows it.
- Chromium not found: set `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright`.
- uv errors about pydantic_core: run through `make`, which strips `PYTHONPATH` and `VIRTUAL_ENV`.
- `ui-locator` FAIL after a UI change: run `make verify-lint`. If it reports a renamed string, update `UI_HANDLES` in `checks.py` and the feature doc. Otherwise the UI regressed.
- Debug by hand: `verify.py launch` prints the console URL and a password. When you're done, run `verify.py cleanup`.
