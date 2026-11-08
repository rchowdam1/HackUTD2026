# Safe Signal: slides (4)

Numbers stay as `[placeholders]` until H+12; fill them only from `results/latest.md` on sealed H1.

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
- Hard-benign false alerts: keyword baseline (K) `[x of n]` vs Safe Signal (B) `[x of n]`
- Scams caught: K `[x of n]`, B `[x of n]` (Wilson 95% CI `[lo-hi]`)
- Paired: `[k]` calls only K got right, `[b]` only B got right. `[win called | no win called]`
- Small print: "60 held-out scripted calls written by a teammate who never saw the rules. Scripted transcripts, not ASR. Too small for a production claim."
- Side card, "Where we fail": `[missed scam types from results/latest.md]`

## 4. Stack and next steps
**Stack:** replayed call audio -> faster-whisper small.en (CPU) -> rules + policy (pure Python, versioned YAML) -> SMS via Twilio (or simulated) -> operator console (React). FastAPI, SQLite: counts and hashed numbers only, no audio or transcripts stored.

**Next:**
- Carrier routing on the Live Translation (*87) path, so it works on any phone
- An in-call audio prompt, not just a text
- A consent gate, with caller notice in all-party-consent states
- Sender verification for our alert texts

Enrollment card shown on this slide: see `enrollment-card.md`.
