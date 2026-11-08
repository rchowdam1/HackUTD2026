# Safe Signal: slides (4)

Numbers from `results/latest.md`: sealed H1, policy v1.0, main `fefb2d3`, scripted transcripts. Update them only from a new eval run.

## 1. The problem
**Title:** A call gets past Scam Shield. Then it asks for your code.
- The caller ID looks fine and nothing on the network flags it.
- Thirty seconds in, the caller asks you to read back the code that was just texted to you.
- Visual: a phone showing an incoming call, then a speech bubble saying "read me the code".

## 2. Demo
**Title:** Live demo
- [placeholder: live console plus phone. Replay 1 (clinic) stays silent. Replay 2 (bank) triggers the alert and the follow-up, and the judge types WRONG]
- Footer: "Replayed calls. Carrier signal mocked. SMS [real | simulated]."

## 3. One number
**Title:** Fewer false alarms on calls that only mention codes or money
- Hard-benign false alerts: keyword baseline (K) 6 of 22 vs Safe Signal (B) 0 of 22 (upper bound 14.9%)
- Scams caught: K 9 of 30 (30.0%, 95% CI 16.6% to 47.9%), B 5 of 30 (16.6%, 95% CI 7.3% to 33.6%)
- Paired: 4 calls only K got right, 6 only B got right. No win called (needs 5 or more in one direction).
- Small print: "60 held-out scripted calls written blind by an AI agent that never saw the rules. Scripted transcripts, not ASR. Too small for a production claim."
- Side card, "Where we fail": B missed 25 of 30 held-out scams (code 9 of 12, payment 9 of 10, remote access 7 of 8). The same rules catch 19 of 20 on the dev set they were tuned on, so they don't yet generalise to new wording. The intent model (arm C) caught no extra scams (5 of 30) and added 1 hard-benign false alert.

## 4. Stack and next steps
**Stack:** replayed call audio -> faster-whisper small.en (CPU) -> rules + policy (pure Python, versioned YAML) -> SMS via Twilio (or simulated) -> operator console (React). FastAPI, SQLite: counts and hashed numbers only, no audio or transcripts stored.

**Next:**
- Carrier routing on the Live Translation (*87) path, so it works on any phone
- An in-call audio prompt, not just a text
- A consent gate, with caller notice in all-party-consent states
- Sender verification for our alert texts

Enrollment card shown on this slide: see `enrollment-card.md`.
