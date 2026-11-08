# CallSafe: slides (4)

Headline numbers come from the blind set H4 (6228 scripted calls, kept outside the repo, sealed by hash `12c97213f185d3d7...` before scoring): K and B scored on main `bfc510b` (same detection code as `ebcb159`), C on the PR #79 branch before its rebase (`79b6b8d`). H1 numbers come from `results/latest.md` (H1 reused). All are scripted transcripts. Update them only from a new eval run. Never quote the invalid 86.8% arm C run on merged code.

## 1. The problem
**Title:** A call gets past Scam Shield. Then it asks for your code.
- The caller ID looks fine and nothing on the network flags it.
- Thirty seconds in, the caller asks you to read back the code that was just texted to you.
- Visual: a phone showing an incoming call, then a speech bubble saying "read me the code".

## 2. Demo
**Title:** Live demo
- [placeholder: live console with the phone frame (simulated SMS). Replay 1 (clinic) stays silent. Replay 2 (bank) triggers the alert and the follow-up, and the judge presses WRONG]
- Footer: "Replayed calls. Carrier signal mocked. SMS simulated."

## 3. One number
**Title:** Keywords alert on 64% of harmless calls. CallSafe alerts on 0.9%.
- False alerts on harmless calls: keyword baseline (K) 2001 of 3111 (64.4%, 95% CI 62.6% to 66.0%) vs CallSafe rules (B, the demo) 27 of 3111 (0.9%, 95% CI 0.5% to 1.3%)
- Scams caught: K 2629 of 3117 (84.3%, 95% CI 83.0% to 85.6%), B 2056 of 3117 (65.9%, 95% CI 64.2% to 67.7%)
- Arm C (opt-in, sends call text to TypeSafe's API): 3094 of 3117 caught (99.2%, 95% CI 98.8% to 99.6%), 9 of 3111 false alerts (0.3%, 95% CI 0.1% to 0.6%), measured on the pre-merge branch. Currently unavailable: the API is out of credit.
- Small print: "6228 scripted calls (3117 scam, 3111 harmless) written blind by 25 isolated AI agents with no repo access, sealed by hash before scoring. Scripted transcripts, not ASR, not real calls. No production claim."
- Side card, "Where we fail": B misses 1061 of 3117 blind scams, about a third. Arm C catches most of those, but it sends call text off the machine and is unavailable today. On the 40-call dev set the rules were tuned on, B catches 20 of 20 with 0 false alerts. On H1 (60 calls; H1 reused: read while diagnosing, so not fully blind) B catches 18 of 30 with 0 of 22 hard-benign false alerts, K 27 of 30 with 13 of 22; no win called.

## 4. Stack and next steps
**Stack:** replayed call audio -> faster-whisper small.en (CPU) -> rules + policy (pure Python, versioned YAML) -> SMS via Twilio (simulated in the demo) -> operator console (React). FastAPI, SQLite: counts and HMAC-hashed numbers only, no audio or transcripts stored. Optional arm C adds TypeSafe's API (sends call text out; off in the demo).

**Next:**
- Carrier routing on the Live Translation (*87) path, so it works on any phone
- An in-call audio prompt, not just a text
- A consent gate, with caller notice in all-party-consent states
- Sender verification for our alert texts

Enrollment card shown on this slide: see `enrollment-card.md`.
