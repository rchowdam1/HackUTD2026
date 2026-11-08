---
name: maintain-verification
description: "Keep Safe Signal's verification honest as the code changes: map git diffs to verify-app features, detect stale recipes and selectors, re-drive affected features live, rerun the TLA+ pipeline check, and ship one PR of proven verification fixes without masking app bugs. Use after merges, before a release/demo, when verify-app fails in a way that smells like drift, or for 'audit the verify skill'."
---

# Maintain the verification skills

Targets, both in `.agents/skills/`: `verify-app` (live journeys + feature map) and `verify-pipeline-formal` (TLA+ model of `pipeline.py`). A feature map rots the moment the app changes; this is its upkeep loop. The unit of rigor is the feature: every affected feature gets a source review and a live drive. Work from the repo root of your own worktree (AGENTS.md: own branch, own worktree).

## Outcomes

Report exactly one, and say which:

- **clean**: every planned feature got source and live coverage, the formal check is in sync, nothing to change. No branch, no PR.
- **changed**: one PR of proven corrections to the verification skills (docs, coverage map, harness, model).
- **blocked**: coverage could not finish or a fix could not be proven. Name the exact blocker (missing tool, external dependency, a check you couldn't run).

Product bugs found along the way are reported in every outcome; they are never "fixed" here.

## Edit scope

Edit only `.agents/skills/verify-app/**`, `.agents/skills/verify-pipeline-formal/**` and this skill. Never edit product code (`backend/`, `console/`, `policy/`, `scenarios/`, `eval/`, `scripts/`). When the app no longer does what a recipe says, decide which it is (step 5) before touching anything. Never weaken an assertion, delete a check, shrink a model bound, or move a check to `external` to make a run pass; the only legitimate reasons are a documented, intended change of behavior (cite the commit, test or PRD section) or a proven harness defect.

## Pass

0. **Plan.** `python3 .agents/skills/maintain-verification/scripts/plan.py` (incremental: each feature against its own `synced_commit`), `--base origin/main` (a PR's changes), or `--all` (periodic full pass). It is read-only and writes `.verify/maintenance/<ts>/plan.{json,md}`: lint errors/warnings, features to re-check with the changed files, unmapped changed files, formal staleness, the live command, and one source-review brief per feature. Read the plan before anything else. If the plan lists no features, no unmapped files, no lint findings and an in-sync formal check, the pass is **clean** after step 4's smoke run.

1. **Index hygiene.** Fix every lint ERROR that is pure bookkeeping (README link, unregistered doc, check ID missing from its doc, H2 order, dead path glob after a rename you can see in `git log --follow`). `make verify-lint` must print `LINT OK`. A lint error that says a UI handle or route vanished is not bookkeeping: carry it into step 3 as suspected drift.

2. **Source wave (parallel, read-only).** For each planned feature, hand its brief from `plan.md` to a read-only subagent, all at once (Hermes `delegate_task` with one task per feature; Claude Code Task tool; Codex/Cursor subagents). Subagents never drive the app, never edit, never run git commands that change state. Each returns: feature summary / source entry points / likely drift with `file:line` / uncovered new behavior / one live recipe. Without subagent support, do the same reviews yourself, one feature at a time. For unmapped files, review them the same way and decide: new user-facing surface (needs a feature or a sub-feature + check), covered by an existing feature (add the path), or not user-facing (add to `ignored_paths` with a reason in the commit message). Require a concrete source path before calling something missing.

3. **Reconcile.** Every planned feature has a returned review. Spot-check each cited drift in the source yourself; don't re-prove clean claims. Merge recipes into as few app states as possible; the harness already orders checks to share one instance.

4. **Live pass (serialized).** One run, never two at once: the harness's lock enforces this (a second run is BLOCKED, not queued). Use the plan's live command, which always includes `--negative-control`:
   `make verify ARGS="--features <planned,features> --negative-control"`
   For a clean plan, still run `make verify ARGS="--features operator-login,call-replay --negative-control"` as a smoke test. The harness launches, runs doctor before the first drive and after every FAIL, relaunches once if the instance went bad, and cleans up in a `finally`. After the run, confirm: `control.invalid-assertion` is FAIL (otherwise stop: the harness can't fail and nothing it says can be trusted), the report's `cleanup.leftover_processes` is empty, `isolation.untouched` is true, and the evidence files listed in `report.json` exist. Formal: `make verify-formal` whenever the plan shows covered files changed, otherwise optionally.

5. **Triage every non-PASS** (read the check's reason, category, assertions, screenshot and `events-*.jsonl`):
   - **Doc drift**: the app does something different on purpose (commit message, test, PRD say so). Update the recipe, the check's expectation and `UI_HANDLES`/`API_ROUTES`. Cite the evidence in the PR.
   - **Harness gap** (category `ui-locator`, `harness-error`, `precondition`, or a doctor failure): the app works when driven by hand (`verify.py launch`, open the console URL, try it) but the harness can't drive or observe it. Fix the harness; helpers stay executable and documented in `verify-app/SKILL.md`.
   - **Verification infrastructure** (`launch` category, missing Playwright/Chromium/whisper model/Java, npm failures): fix the environment or report **blocked** with the exact missing piece. Never mark these PASS.
   - **Product regression** (category `app-behavior` with the app driven correctly, or a formal property violated on an accurate model): the app broke a promise. Record it with the failing check ID, observed vs expected, evidence paths, and the commit that introduced it (`git log -L`/`git bisect` with `make verify ARGS="--checks <id>"`). Leave the check failing. Tell the owning track (AGENTS.md: ASK on the board to the owner). Only once the owner tracks it in an issue may you register the check with `known_gap="#<issue> <summary>"` (never weaken the assertion): it then reports KNOWN-GAP instead of failing CI; remove the marker when a report says it passed.
   - **Formal**: follow "When code changes" in `verify-pipeline-formal/SKILL.md` (model drift vs code bug, rerun the matching `broken-*` config after any model change).
   Every harness or doc fix gets re-driven live (same command, the affected checks only) before it ships; the last drive of the pass is what the PR claims.

6. **Sync and ship.** On a clean tree at the commit you verified (commit the verification changes first, then re-run the affected checks if the harness changed): `env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --with playwright==1.64.1 python .agents/skills/verify-app/scripts/verify.py sync` moves `synced_commit` forward for features whose checks all passed in the latest report; it refuses dirty or mismatched runs. Move the formal sync commit by hand only after `make verify-formal` printed `FORMAL OK` on a model you confirmed describes the code. For **changed**: one PR (`Refs`/`Closes` the maintenance issue) containing only verification-skill changes, listing what was checked, what changed and why, the report run IDs, product bugs found, and what remains unverified. For **clean**/**blocked**: no PR; report the outcome, coverage and blockers.

## Report

State: the outcome; features covered (source + live) and their final status; the run IDs (`.verify/runs/<id>/report.md`) and formal evidence dir; each drift fix and its evidence; product bugs (check ID, steps, observed vs expected, introducing commit); external items still unverified (`coverage.json` → `external`); and exactly how to reproduce each failure (`report.json` → `reproduce`). Keep run notes in `.verify/maintenance/<ts>/` (git-ignored); don't commit them.

## Cadence and CI

- Every PR touching mapped paths: CI runs `make verify-lint` and `make verify-changed` (`.github/workflows/verify.yml`, path-filtered, so docs-only PRs cost nothing).
- After a merge window or before judging: run this skill with `--base` set to the last synced commit or `--all`.

Human-facing overview (prerequisites, statuses, CI, troubleshooting): `docs/verification.md`. Keep it in step when this skill changes.
