# AGENTS.md

Guidelines for AI coding agents working in this repo. They are based on Andrej Karpathy's observations about common LLM coding pitfalls.

These rules favor caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

- State your assumptions explicitly. If uncertain, ask.
- If a request has multiple interpretations, present them. Don't pick one silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing and ask.

## 2. Simplicity First

**Write the minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you wrote 200 lines and it could be 50, rewrite it.

Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match the existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it. Don't delete it.

When your changes create orphans:
- Remove imports, variables, and functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Turn tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass."
- "Fix the bug" → "Write a test that reproduces it, then make it pass."
- "Refactor X" → "Ensure tests pass before and after."

For multi-step tasks, state a brief plan with a check for each step:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you work independently. Weak criteria ("make it work") require constant clarification.

---

## 📌 Message Board: Issue #1 (READ THIS)

**[Issue #1](https://github.com/rchowdam1/HackUTD2026/issues/1) is a SUPER valuable resource.** It's the shared group chat for every teammate and every agent. Treat it as the team's collective memory.

- **Before starting work:** read the board, especially every 💡 LEARN. Someone may have already solved your problem or hit your bug.
- **While working:** post 🟢 CLAIM when you start a task and ✅ DONE when it's finished. Post 🚧 BLOCKED or ❓ ASK if you're stuck.
- **Save learnings:** whenever you figure out something non-obvious, post it as 💡 LEARN so no one solves it twice. That covers gotchas, fixes, API quirks and working commands.
- Follow the format and rules pinned in the issue body. Keep messages succinct, and never post secrets.

```bash
gh issue view 1 --comments                    # read
gh issue comment 1 --body "\`agent-name\` · model · username
TAG message"                                  # post
```

---

## Project Context

_To be filled in once the stack is chosen._

- **What we're building:** TBD
- **Stack:** TBD
- **Setup / run:** TBD
- **Test:** TBD

## 🚦 Parallel Work (up to 100 agents at once)

Up to 100 agents may be working in this repo at the same time. These rules keep that from turning into chaos.

### 1. Own branch, own worktree, never `main`
Every agent works on its own branch named `<username>/<agent-name>`, ideally in its own worktree:
```bash
git fetch origin
git worktree add ../wt-<agent-name> -b <username>/<agent-name> origin/main
```
**Never commit or push directly to `main`.**

### 2. Push early, commit aggressively: unpushed work is lost work
- **Push at the earliest possible stage.** As soon as your branch exists, make a first commit and push it, even if it's empty:
  ```bash
  git commit --allow-empty -m "start <agent-name>" && git push -u origin HEAD
  ```
- **Commit aggressively.** Commit after every small working change, such as a function, a fix, or a file. Don't wait for a feature to be finished. Small commits are cheap, and they get squashed at merge anyway.
- **Push after every commit:**
  ```bash
  git add -A && git commit -m "<what changed>" && git push
  ```
- **Never sit on uncommitted work.** If more than ~5 minutes of changes aren't pushed, stop and push them now.
- **Push everything before you stop** for any reason, including finishing, getting blocked, erroring out, or running low on context.

### 3. Claim ownership before you touch files
- Your 🟢 CLAIM on the [board](https://github.com/rchowdam1/HackUTD2026/issues/1) must list your **branch** and the **files or directories** you'll own.
- Read the board first. If another active CLAIM overlaps your paths, don't touch them. Pick other work, or ❓ ASK the owner.
- A claim ends with ✅ DONE. A claim with no posts for **60 min** is stale, so post 📢 FYI that you're taking it over before you do.
- **Shared hotspot files** are package manifests, lockfiles, configs, DB schema and shared types. Keep edits to them minimal and additive, and post 📢 FYI when you change one.

### 4. Merge small, merge often
1. Rebase onto the latest main: `git fetch origin && git rebase origin/main`. Resolve conflicts on **your** branch. Keep both sides' intent, and never just discard someone else's code.
2. Verify that it builds and tests pass.
3. Push with `git push --force-with-lease`. That's only ever for your own branch, never for `main` or anyone else's branch.
4. Open a PR and squash-merge it: `gh pr create --fill && gh pr merge --squash --delete-branch`.
5. Post ✅ DONE with the PR link.

**`main` must always build and run.** If your merge breaks it, fixing it is your top priority, and you should post 🚧 BLOCKED or 📢 FYI right away.

### 5. Basics
- Keep PRs small and focused on one task each. Small PRs merge cleanly, and big ones conflict.
- Never commit secrets such as API keys or `.env` files.
