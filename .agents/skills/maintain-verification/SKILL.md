---
name: maintain-verification
description: "Keep CallSafe's verify-app checks and the TLA+ pipeline model true as the code changes, without masking app bugs. Use when verify-app fails in a way that looks like drift, or when a human asks for a verification audit."
---

# Maintain the verification skills

Use this only when a check fails because of drift, or when a human asks. Don't run it as routine upkeep.

1. **Plan.** `python3 .agents/skills/maintain-verification/scripts/plan.py --base origin/main` (or `--all`). It's read-only and writes `.verify/maintenance/<ts>/plan.md`: lint findings, affected features, unmapped files and whether the formal model is stale.
2. **Lint.** Fix the bookkeeping errors until `make verify-lint` prints `LINT OK`. If a UI handle or route vanished, treat it as possible drift and look at it in step 4.
3. **Drive.** `make verify ARGS="--features <affected> --negative-control"`. `control.invalid-assertion` must FAIL. If it doesn't, the harness can't detect failures, so stop. Run `make verify-formal` if the plan says the model is stale.
4. **Triage each non-PASS:**
   - The app changed on purpose (a commit, test or the PRD says so): update the recipe and the check.
   - The harness can't drive something that works by hand: fix the harness.
   - A tool or model is missing: report BLOCKED with what's missing.
   - The product broke: leave the check failing and tell the owner. Mark it `known_gap` only once an issue tracks it.
5. **Ship.** Commit, rerun the affected checks, run `verify.py sync`, and open one PR that changes only `.agents/skills/**`.

Edit only `.agents/skills/verify-app/**`, `.agents/skills/verify-pipeline-formal/**` and this skill. Never edit product code, weaken an assertion, delete a check or shrink a model bound to get a pass.
