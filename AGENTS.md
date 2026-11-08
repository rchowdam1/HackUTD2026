# AGENTS.md

CallSafe texts you during a call when the caller asks for a code, money or access. `PRD.md` §19 is the spec. Stack: Python 3.11 FastAPI (`backend/app`), React/Vite console (`console/`), SQLite, uv.

## Scope

This is a hackathon. Build what the 3-minute demo and the judges see.

- Don't harden against edge cases that won't happen on stage.
- Don't start new eval sets, accuracy targets, verification frameworks or tooling follow-ups unless a human asks for them.
- If you're not sure something is needed, ask a human before you build it.

## Done means verified

```bash
make smoke            # ruff + pytest + OTP fixture replay. Must pass before any PR.
make verify-changed   # drives the real app for the features you touched (UI/API changes)
```

Your PR body says what changed and the command that proved it works. If you can't run the check, say BLOCKED and why. Don't claim it passed.

## The codebase is memory

Agents copy what's already here, so every pattern in the repo gets repeated.

- Extend the existing primitives. Don't build parallel ones: `app.policy.templates.get` for SMS copy, `app.events.emit` for events, `app.sms.get_gateway()` for sending, `require_operator` for auth.
- If you hit a bad pattern, fix it or leave it alone. Don't copy it.
- When a mistake can recur, stop it with a mechanism and not a sentence. In order of preference: change the code or types so the mistake can't be written, then add a test or a ruff rule (`[tool.ruff]` in `pyproject.toml`), and only if neither works add one line here. Rules that can be checked automatically belong in `make smoke`, not in this file.

## Code

- Write the smallest change that does the job. Don't add abstractions, config flags, fallbacks or error handling for cases that can't happen.
- Touch only what the task needs. Delete anything your change leaves unused.
- Comments explain why, never what the code does.
- Never read `scenarios/H1/` (the sealed test set). Never commit secrets or `.env`.

## Workflow

- Each task is a GitHub issue labelled `track-a/b/c`. Claim it by adding the `claimed` label and posting a one-line CLAIM comment with your branch and the paths you own. Don't edit paths that someone else has claimed. Post an ASK to the owner instead.
- Branch `<username>/<agent-name>` in its own worktree off `origin/main`. Never touch `main`. Push after every commit.
  ```bash
  git worktree add ../wt-<agent-name> -b <username>/<agent-name> origin/main
  ```
- Before a PR: `git rebase origin/main`, `make smoke`, `git push --force-with-lease`, then `gh pr create --fill --body "Closes #<n>"`. Humans merge.
- Keep edits to shared files (`pyproject.toml`, `uv.lock`, `Makefile`, `models.py`, `.env.example`) minimal, and post an FYI on the board when you make one.

## Message board

[Issue #1](https://github.com/rchowdam1/HackUTD2026/issues/1). Its body has the message format and the current team facts, so read it before you start. Post only LEARN, FYI, ASK, BLOCKED or REPLY, at most 3 lines each. Don't post progress, thanks or acknowledgements. Answer messages addressed to you.

## Verification skills

In `.agents/skills/` (also `.claude/skills/`): `verify-app` drives the real app in a sandbox, `maintain-verification` keeps its checks true, and `verify-pipeline-formal` model-checks `pipeline.py`. Never weaken a check to make it pass. If a check FAILs in someone else's area, report it to the owner.
