# AGENTS.md

Rules for AI coding agents in this repo. They are based on Andrej Karpathy's observations about LLM coding pitfalls.

## 1. Think Before Coding

- State your assumptions. If you're uncertain, ask.
- If a request has multiple interpretations, present them instead of picking one silently.
- If a simpler approach exists, say so.
- If something is unclear, stop and ask.

## 2. Simplicity First

- Write the minimum code that solves the problem.
- Don't add features, abstractions or configurability that weren't requested.
- Don't add error handling for impossible cases.
- If 200 lines could be 50, rewrite it.

## 3. Surgical Changes

- Touch only what the task requires. Don't refactor or reformat unrelated code.
- Match the existing style.
- Remove imports, variables and functions that your change made unused. If you notice unrelated dead code, mention it and leave it in place.
- Every changed line should trace directly to the request.

## 4. Goal-Driven Execution

- Turn each task into a verifiable goal. For example, "fix the bug" becomes "write a failing test, then make it pass."
- For multi-step tasks, state a short plan with a check for each step.
- Keep working until the checks pass.

## 5. Message Board (Issue #1)

[Issue #1](https://github.com/rchowdam1/HackUTD2026/issues/1) is the shared chat for all teammates and agents. The message board is a SUPER valuable resource, so use it as the team's memory.

- Before starting work, read the board, especially every LEARN post.
- CLAIM goes on your task issue (see "Task issues" below), not on the board. Post BLOCKED or ASK on the board if you're stuck.
- When you figure out something non-obvious, save it as a LEARN post. That covers gotchas, fixes, API quirks and working commands.
- Post only when the message has real value to someone else. Don't post progress chatter, thanks, or repeats of earlier messages. The board must stay readable with 100 agents on it.
- Follow the message format pinned in the issue. Keep messages short. Never post secrets.

### Communicate like an engineer in a large org
- **Address a message:** write `to:<agent-name>` for an agent, or `@username` for a human. A human mention sends a notification, so use it sparingly.
- **Reply to a message:** use the REPLY tag with `to:<sender>` and `re:<comment-link>`.
- **Check your inbox:** look for messages addressed to your agent name or your username before starting each step, and at least every 15 minutes.
- **Answer every message addressed to you.** Give the answer, or acknowledge it and say when you'll have the answer, or redirect it to the right owner. Never ignore one.
- **Close the loop.** When your question gets answered, reply to confirm it's resolved.
- **Escalate if there's no response.** If you get no reply within 30 minutes, @mention the owner's human. If an agent has disagreed with you twice, or the decision is a product call, @mention the humans.
- **Owners answer for their area.** Whoever holds the claim on a path answers questions about it. If that agent is gone, its human answers.
- **Ask the owner first.** Before you change code that someone else owns, post an ASK to its owner, and wait for the answer or use an approach that doesn't touch their paths.

```bash
# Read the board
gh issue view 1 --comments

# Read your inbox
gh api repos/rchowdam1/HackUTD2026/issues/1/comments --paginate --jq '.[] | select(.body | test("to:<agent-name>|@<username>")) | .html_url + "\n" + .body'

# Post
gh issue comment 1 --body "\`agent-name\` · model · username
TAG to:<agent> re:<comment-link> message"
```

### Task issues
Every agent task is its own GitHub issue. Each one is labelled `track-a`, `track-b` or `track-c`, assigned to the developer who owns the track, and titled `<agent-name>: <task>`. The body holds the assignment, the paths it owns and its "done when".

- **Find work:** list the open, unclaimed tasks for your developer:
  ```bash
  gh issue list --assignee <username> --state open --search "-label:claimed"
  ```
  If your human gave you a task, take that issue.
- **Respect gates:** don't claim an issue labelled `stretch`, or one whose body says "start after H+N", before its gate.
- **Claim:** add the label, then comment CLAIM on the issue (same format as the board). Then re-read its comments. If an earlier CLAIM exists, back off and pick another issue.
  ```bash
  gh issue edit <n> --add-label claimed
  gh issue comment <n> --body "\`agent-name\` · model · username
  CLAIM branch <username>/<agent-name> · owns <paths>"
  ```
- **One agent per issue:** use the agent name and branch in the issue. If that branch already exists from earlier merged work, add `-2`.
- **Link the PR:** put `Closes #<n>` in the PR body when it meets the issue's "done when". Merging then closes the issue. Use `Refs #<n>` for partial work, and comment on the issue with what's left.
- **Stale claims:** a claimed issue with no comments or pushed commits for 60 minutes is stale. Comment FYI on the issue before you take it over.
- **New work:** if no issue covers it, open one in the same format, labelled with your track and assigned to your developer. Then claim it.

## 6. Parallel Work

Up to 100 agents may be working at once.

### Branches
- Work on your own branch named `<username>/<agent-name>`, preferably in its own worktree:
  ```bash
  git fetch origin
  git worktree add ../wt-<agent-name> -b <username>/<agent-name> origin/main
  ```
- Never commit or push to `main`.

### Commit and push
- Push your branch as soon as it exists:
  ```bash
  git commit --allow-empty -m "start <agent-name>" && git push -u origin HEAD
  ```
- Commit after every small working change, and push after every commit:
  ```bash
  git add -A && git commit -m "<what changed>" && git push
  ```
- Never leave more than ~5 minutes of work unpushed.
- Push everything before you stop for any reason.

### Ownership
- Your CLAIM must list your branch and the files or directories you'll own.
- Don't edit paths that another active claim owns. Pick other work, or post an ASK.
- Shared files include package manifests, lockfiles, configs, the DB schema and shared types. Keep your edits to them minimal and additive, and post an FYI when you change one.

### Pull requests
1. Rebase onto the latest main with `git fetch origin && git rebase origin/main`. Resolve conflicts on your branch, keeping both sides' intent.
2. Verify that the build and tests pass.
3. Push with `git push --force-with-lease`. Only ever do this on your own branch.
4. Open a PR with `gh pr create --fill --body "Closes #<n>"` (or `Refs #<n>`), followed by a short what-and-how-verified. Do not merge it, because a human reviews and merges.
5. The linked PR shows up on the task issue, so there's no separate DONE post.

### Basics
- Keep PRs small and limited to one task.
- Never commit secrets such as API keys or `.env` files.

## 7. Verification

Prove a feature works by driving the real app, not by reading code. Project-local skills live in `.agents/skills/` (also reachable as `.claude/skills/`):

- `verify-app`: launches the backend + console in an isolated sandbox (`.verify/`, never your `.env` or `data/`), drives user journeys with Playwright, the API, signed Twilio webhooks and the CLIs, and writes PASS / FAIL / BLOCKED with evidence to `.verify/runs/<id>/report.{json,md}`. Read `.agents/skills/verify-app/SKILL.md`.
- `maintain-verification`: maps git changes to features, detects stale recipes, re-drives affected features, and fixes the verification without hiding app bugs.
- `verify-pipeline-formal`: TLA+ model check of `pipeline.py` ordering guarantees.

```bash
make verify-changed            # features touched since origin/main (run before opening a PR)
make verify                    # everything, ~4 min
make verify-lint               # verification drift, seconds
make verify-formal             # TLA+ pipeline check, seconds
```

BLOCKED is never a pass. Report a FAIL in an area you don't own to its owner; don't edit their code or the check to make it green.

## Project Context

Fill this in once the stack is chosen.

- What we're building: TBD
- Stack: TBD
- Setup / run: TBD
- Test: TBD
