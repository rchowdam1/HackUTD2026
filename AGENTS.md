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
- Post CLAIM when you start a task and DONE when you finish. Post BLOCKED or ASK if you're stuck.
- When you figure out something non-obvious, save it as a LEARN post. That covers gotchas, fixes, API quirks and working commands.
- Follow the message format pinned in the issue. Keep messages short. Never post secrets.

```bash
gh issue view 1 --comments
gh issue comment 1 --body "\`agent-name\` · model · username
TAG message"
```

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
- A claim with no posts for 60 minutes is stale. Post an FYI before you take it over.
- Shared files include package manifests, lockfiles, configs, the DB schema and shared types. Keep your edits to them minimal and additive, and post an FYI when you change one.

### Pull requests
1. Rebase onto the latest main with `git fetch origin && git rebase origin/main`. Resolve conflicts on your branch, keeping both sides' intent.
2. Verify that the build and tests pass.
3. Push with `git push --force-with-lease`. Only ever do this on your own branch.
4. Open a PR with `gh pr create --fill`. Do not merge it, because a human reviews and merges.
5. Post DONE with the PR link.

### Basics
- Keep PRs small and limited to one task.
- Never commit secrets such as API keys or `.env` files.

## Project Context

Fill this in once the stack is chosen.

- What we're building: TBD
- Stack: TBD
- Setup / run: TBD
- Test: TBD
