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

## Team Workflow

- Branch off `main` for features, then open a PR to merge back. Don't push directly to `main` mid-hackathon unless it's agreed.
- Keep commits small and descriptive.
- Never commit secrets (API keys, `.env` files).
