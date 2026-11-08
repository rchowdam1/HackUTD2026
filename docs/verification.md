# Verification guide

Safe Signal has an agent-driven verification system modeled on pstack's `create-verification-skill` and `maintain-verification-skill` (plus the formal pair). It launches the real app, operates it the way the operator, the subscriber's phone and Twilio do, and reports for each check whether the feature actually works, with evidence a reviewer can open.

This guide is for people. Agents should read the skills directly; they are the source of truth and are kept in sync by lint:

| Skill | Path | Use it to |
|---|---|---|
| `verify-app` | `.agents/skills/verify-app/SKILL.md` | prove features work: launch, doctor, drive, evidence, cleanup |
| `maintain-verification` | `.agents/skills/maintain-verification/SKILL.md` | keep the checks true as code changes, without hiding app bugs |
| `verify-pipeline-formal` | `.agents/skills/verify-pipeline-formal/SKILL.md` | model-check the pipeline's ordering guarantees (TLA+) |

`.claude/skills` is a symlink to `.agents/skills`, so Claude Code finds them too. Codex, OpenCode and Hermes read `.agents/skills` or can be pointed at it.

## Quick start

```bash
make verify-changed            # features touched since origin/main (before opening a PR)
make verify                    # all 24 checks across 10 features, about 4 minutes
make verify ARGS="--features call-replay,sms-replies"
make verify ARGS="--checks replay.bank-alert"     # dependencies are added automatically
make verify ARGS="--negative-control"             # adds a deliberately false check that must FAIL
make verify-lint               # drift between docs, map, harness, UI and routes (seconds, no app)
make verify-formal             # TLA+ model check of pipeline.py (about 5 s)
```

Read the result in `.verify/runs/latest/report.md`. Exit codes: `0` every check passed, `1` something failed, `2` nothing failed but something was BLOCKED or nothing ran.

### Prerequisites

| Needed for | What | Notes |
|---|---|---|
| everything | `uv`, Python 3.11 (`make install`) | the harness runs in the project venv |
| console checks | Node 20.19+ (`npm`) | `npm ci` runs inside each sandbox |
| console checks | Chromium for Playwright 1.64.1 | `env -u PYTHONPATH -u VIRTUAL_ENV uv run --with playwright==1.64.1 playwright install chromium` |
| `asr-replay`, `preflight.model` | faster-whisper `small.en` cached in `~/.cache/huggingface` | download once online (see `scripts/preflight_checks.py`); override with `VERIFY_HF_HOME` |
| `make verify-formal` | Java 11+ | `tla2tools.jar` v1.8.0 downloads to `.verify/tools/` (sha256-pinned) |

If something is missing, the affected checks come back BLOCKED with the exact reason. They are never reported as passing.

## What it does to your machine

- **It never runs the app from your checkout.** The app writes `data/safesignal.db` and `results/` relative to its own source path. So each run copies the working tree, including uncommitted edits but not ignored files or `scenarios/H1/`, into `.verify/sandbox/<run_id>/` and runs from the copy. Before and after each run the harness fingerprints your `data/` and `results/`; any change fails the run as an isolation breach.
- **It never reads `.env` and never texts anyone.** The sandbox gets random operator, session and salt secrets, a token used only for signing webhooks, and fictional numbers (`+15550100001` and `+15550100002`). It has no Twilio account SID, so even "real" SMS mode fails closed.
- **It uses free ports, never 8000 or 5173.** Your own `make run` or demo instance keeps running untouched.
- **One run at a time.** `.verify/lock` makes a second run report BLOCKED instead of sharing an instance.
- **It only kills what it started.** Cleanup kills a process group only if its PID and command line point at this run's sandbox, then deletes the sandbox. Evidence in `.verify/runs/` is kept; delete old runs by hand.
- `.verify/` is git-ignored.

## What is covered

| Feature | Checks | How it is driven | How it is confirmed independently |
|---|---|---|---|
| Operator login | `login.api-guard`, `login.ui-wrong-password`, `login.ui-success` | password form, unauthenticated / forged-cookie API calls | 401s, cookie flags, no session started (SSE) |
| Call replay | `replay.clinic-silent`, `replay.bank-alert` | `Run clinic` / `Run bank` buttons | SSE event order, simulated outbox, template texts, Why panel vs decision |
| SMS replies | `replies.opt-in-yes`, `replies.wrong-counter`, `replies.shared`, `replies.keyword-normalise`, `replies.stop-blocks-alerts` | phone frame YES / WRONG / SHARED / STOP, `/sms/simulate-inbound` | SQLite consent (recomputed salted hash), `reply_counts`, `/aggregates`, outbox |
| Call controls | `controls.end-call-midway`, `controls.reset-midway`, `controls.sms-mode-toggle`, `controls.sms-mode-after-reload` | End call / Reset mid-replay, SMS mode toggle | no late events or SMS after reset, consent and counts unchanged in SQLite, mode in the next `session running` event |
| Results card | `results.pending`, `results.eval-cli-to-card` | `python -m eval.run --arms K,B --batch dev` | file bytes equal `GET /results/latest`; card numbers equal the file |
| Twilio webhooks | `webhooks.signature-required`, `webhooks.signed-inbound-dedupe`, `webhooks.status-callback` | form posts signed with Twilio's algorithm (written independently of the app) | 403s, reply/sms events, SQLite counts, MessageSid dedupe |
| Enrollment invite | `invite.demo-and-spare` | `POST /sms/invite` | SQLite `invited` rows by hash, no raw number anywhere in the DB file |
| Fixture replay | `fixtures.console-replay` | console `?fixtures` | transcript from `tests/fixtures/events`, no backend calls |
| ASR replay | `asr.bank-replay` | separate instance with `REPLAY_SOURCE=asr` | every segment `source: asr` (no silent cached fallback), ALERT-OTP-01 |
| Preflight | `preflight.offline-checks`, `preflight.model` | `scripts/preflight_checks.py --no-sms` | PASS/FAIL lines, exit code, no secrets printed |

The step-by-step recipe for each feature (preconditions, handles, expected results, gotchas) is in `.agents/skills/verify-app/features/<feature>.md`. Source-to-feature mapping, paths that force a full run, ignored paths and sync commits are in `features/coverage.json`.

**Not verified by automation** (listed in every report): real Twilio SMS to a phone; Twilio webhooks through the cloudflared tunnel, plus `scripts/demo_up` and `scripts/sms_kill_check.py`; Twilio's own STOP handling; arm C in a live call (no user path selects it); H1 scoring (agents may not read `scenarios/H1/`); voice generation; physical demo setup. Those remain human checks (`docs/twilio-live.md`, `scripts/preflight`).

## Reading a report

`.verify/runs/<run_id>/` contains:

- `report.md` / `report.json` (schema `verify-app/report@1`): the verdict, then for each check its status, reason, failure category, every assertion (expected and observed), actions, timestamps and artifact paths. Also the doctor results, environment (commit, dirty flag, snapshot digest, tool versions), isolation fingerprint, cleanup result, per-feature coverage, unverified external items, and `reproduce` commands for anything that did not pass.
- `screenshots/<check>--<state>.png` plus `.aria.txt` (accessibility snapshot), taken at each proof point and on every non-PASS.
- `events-<profile>.jsonl` (every server event, with receive time), `backend-*.log`, `vite-*.log`, `commands.log`, `artifacts/` (API dumps, CLI transcripts).

Statuses:

| Status | Meaning | Fails the run? |
|---|---|---|
| PASS | every assertion held (at least one ran) | no |
| FAIL | the app did something other than expected | yes (exit 1) |
| BLOCKED | could not run: missing tool or model, launch failure, unmet precondition, harness exception | exit 2 (`--allow-blocked` makes it 0, used in CI) |
| KNOWN-GAP | an app-behavior failure of a check marked `known_gap="#<issue> ..."` for a product bug tracked in that issue; the assertion itself is unchanged | no; listed under "Known product gaps", and flagged if it unexpectedly passes so the marker gets removed |

FAIL categories help with triage:

- `app-behavior`: a wrong value.
- `ui-locator`: a button or text is missing. Either the UI regressed or the map drifted; `make verify-lint` and the screenshot tell which.
- `app-unreachable`: a request to the app failed outright.
- `ui-stream`: the console never received a live event.

## Keeping it true (maintenance)

```bash
python3 .agents/skills/maintain-verification/scripts/plan.py              # incremental, from per-feature sync commits
python3 .agents/skills/maintain-verification/scripts/plan.py --base origin/main
python3 .agents/skills/maintain-verification/scripts/plan.py --all        # periodic full pass
```

The planner is read-only. It writes `.verify/maintenance/<ts>/plan.{md,json}` with:

- lint findings,
- the features whose covered files changed (and why),
- changed files no feature covers (possible new user-facing surface),
- whether the formal model's covered files changed since its sync commit,
- one source-review brief per feature, ready to hand to parallel read-only subagents.

The skill then:

1. Reconciles the subagents' reviews.
2. Runs one serialized live pass with the negative control.
3. Triages every non-PASS as doc drift, a harness gap, verification infrastructure, or a product regression. Product regressions stay failing and go to their owner. Only once the owner tracks one in an issue may it be marked `known_gap`.
4. Records the new sync commits with `verify.py sync`. This refuses dirty or mismatched runs and never syncs a failing feature.

The rule that matters: never weaken an assertion, delete a check, shrink a model bound, or move something to "external" to make a run pass.

## CI

`.github/workflows/verify.yml` runs on pull requests that touch app or verification paths (backend, console, policy, demo and dev scenarios, eval, scripts, audio, event fixtures, the verify-app skill, Makefile, Python lockfile). Docs- and deck-only PRs don't start it. It runs:

1. `make verify-lint`.
2. `verify.py affected --base origin/<base>`.
3. A Chromium install, only if a console feature is affected.
4. `make verify-changed` with `--allow-blocked`.

FAIL fails the job. BLOCKED and KNOWN-GAP show in the job summary, and the evidence is uploaded as the `verify-evidence` artifact (kept 7 days). On GitHub runners there is no whisper model, so `asr-replay` and `preflight.model` report BLOCKED there; run them locally.

## Formal check of the pipeline

`model/Pipeline.tla` models `pipeline.py`, the replay loop and the `/demo` routes, with one step per stretch of code between `await`s. The worker-thread SMS send is modelled as two steps: the live check, then the gateway call. TLC explores every interleaving within 2 segments, 2 replays and 2 operator requests.

- **Proved within those bounds on the real code:** at most one follow-up per call, one "finished" per call, no events after a call goes stale, the follow-up goes out after the alert, no alert after "finished", and a send reaches the gateway only if its call was live when the thread checked.
- **Shown to be able to fail:** each property breaks on a variant with one guard removed (`broken-*` configs).
- **Finding:** PRD §19.10 says stale sessions "never send SMS". The code can't guarantee that. If Reset lands after the worker thread's `_live()` check, that alert still goes out (the window covers the consent read plus the Twilio request). See the formal skill for the counterexample.

## Current status

- **Status at merge** (main `2b92a74`, 2026-11-07 CST, run `20261108T023128Z-1b38`): 23 PASS, 0 FAIL, 0 BLOCKED, 1 KNOWN-GAP. With `--negative-control`, `control.invalid-assertion` FAILed as designed. The checkout's data was untouched and no processes were left behind. `make verify-formal`: FORMAL OK (all 7 configs as expected). Reproduce with `make verify ARGS="--negative-control"` and `make verify-formal`.
- **Known product gaps** ([#64](https://github.com/rchowdam1/HackUTD2026/issues/64), Track B):
  - After a page reload the console shows `simulated` while the backend is in `real` (`controls.sms-mode-after-reload`, KNOWN-GAP).
  - `/sms/inbound` and `/sms/status` accept any request signed with an empty key when `TWILIO_AUTH_TOKEN` is unset. No live check covers this yet, because the sandbox always sets a token.
- **Pipeline finding:** reset versus an in-flight send, as described above (Track A to decide: change the PRD wording or the design).

## Troubleshooting

- **`BLOCKED: another verification run holds .verify/lock`**: a run is in progress. `verify.py status` shows it; wait for it to finish.
- **`a launched instance is still running`**: a manual `verify.py launch` is still up. Run `verify.py cleanup`.
- **Chromium not found even though it is installed**: Playwright looks in `$XDG_CACHE_HOME/ms-playwright`. If your shell overrides `XDG_CACHE_HOME`, set `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright`.
- **`uv` errors about pydantic_core or a foreign venv**: always run through `make` or the `env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV` prefix.
- **A check fails with `ui-locator` after a UI change**: run `make verify-lint`. If it names the renamed string, update `UI_HANDLES` in `checks.py` and the feature doc together (an intended rename). Otherwise the UI regressed.
- **Debugging a failure by hand**:
  1. `verify.py launch` prints the console URL and a throwaway password.
  2. Reproduce the steps from the feature doc in the console.
  3. Run `verify.py doctor`, then `verify.py cleanup`.
  4. To keep the sandbox for inspection, rerun with `ARGS="--checks <id> --keep-sandbox"`.

Everything above runs as `env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --with playwright==1.64.1 python .agents/skills/verify-app/scripts/verify.py <command>`.
