# CallSafe: slides (4)

Numbers come from two sources only, labelled on the slide. **Dev:** `results/latest.md`, 40 scripted calls (20 scam, 20 harmless, 13 of them hard-benign) that the rules were tuned on, arms K, B and C (C = Perplexity Decider V1.2). **H4 blind:** 6228 scripted calls, kept outside the repo, sealed by hash `12c97213f185d3d7...` before scoring; K and B scored on main `bfc510b` (same detection code as `ebcb159`), C on the PR #79 branch before its rebase (`79b6b8d`) with TypeSafe Jev 1.14, the previous arm C model. All are scripted transcripts, not real calls. Update them only from a new eval run. Never quote the invalid 86.8% arm C run on merged code. No latency number on any slide: the console shows the measured one.

## 1. The problem
**Title:** A call gets past Scam Shield. Then it asks for your money.
- The caller ID looks fine and nothing on the network flags it.
- Thirty seconds in, the caller asks you to send money or read back the code that was just texted to you.
- Visual: a phone showing an incoming call, then a speech bubble saying "go to the bank and take out whatever you can spare".

## 2. Live call
**Title:** You're the scammer.
- [placeholder: live console. A judge calls our Twilio number and reads the grandson script; Arnav's phone rings and he answers. Both sides are transcribed live. Rules stay silent; Perplexity Decider flags the money request mid-call (the Why panel's "Caught by: Perplexity Decider (AI): N% sure", N as the console shows it) and quotes the line; the alert is sent to Twilio, Arnav hangs up and the follow-up is sent.]
- Footer: "Live call through a Twilio number we own, forwarded to the subscriber's phone; not a carrier integration. Alert texts are sent through Twilio for real, but US carriers block them today (Twilio error 30034: our number's 10DLC registration isn't done, which takes days), so the console's Outgoing texts panel shows exactly what was sent and the status Twilio reports: failed. AI on: each caller turn plus up to three turns before it goes to OpenRouter."

## 3. The numbers
**Title:** Keywords alert on 64.4% of harmless calls. CallSafe rules alert on 0.9%.
- **Blind H4 set (6228 scripted calls):** keywords (K) catch more scams, 2629 of 3117 (84.3%), but alert on 2001 of 3111 harmless calls (64.4%). CallSafe rules (B) alert on 27 of 3111 (0.9%) and catch 2056 of 3117 (65.9%).
- **Rules + AI (C) on H4:** 3094 of 3117 caught (99.2%), 9 of 3111 false alerts (0.3%). Measured on the pre-merge branch with TypeSafe Jev 1.14, the previous arm C model; not re-measured with Perplexity Decider V1.2, which the demo runs.
- **Dev set (40 scripted calls the rules were tuned on):** false alerts on the 13 hard-benign calls: keywords 11 of 13, CallSafe rules 0 of 13, rules + AI 0 of 13. All three catch 20 of 20 scams. Dev shows no AI gain because the rules were tuned on it.
- Small print: "H4: 6228 scripted calls (3117 scam, 3111 harmless) written blind by AI agents with no repo access, sealed by hash before scoring. Dev: 40 scripted calls the rules were tuned on. Scripted transcripts, not ASR, not real calls. No production claim."
- Side card, "Where we fail": on H4 the rules alone miss about a third of the scams, and keywords catch more. The grandson call is one the rules miss. The AI catches that kind of request, but it sends call text off the laptop, and its H4 number was measured with the previous model.

## 4. Stack and next steps
**Stack:** caller dials a Twilio number we own -> Twilio forwards the call to the subscriber and streams both sides' audio to the laptop -> faster-whisper small.en (CPU, on the laptop) -> rules + policy (pure Python, versioned YAML) + Perplexity Decider V1.2 through OpenRouter (each caller turn plus up to three turns before it) -> alert text via Twilio (sent for real; carrier-blocked until 10DLC registration) -> operator console (React). Fallbacks: "Live (mic)" push-to-talk in the console (if it is in the merged console), then the recorded "Run grandson" replay, through the same pipeline. FastAPI, SQLite: counts and HMAC-hashed numbers only, no audio or transcripts stored.

**Next:**
- Carrier routing on the Live Translation (*87) path, so it works on any phone
- An in-call audio prompt, not just a text
- A consent gate, with caller notice in all-party-consent states
- Finish 10DLC registration and verify our sender, so the alert text arrives

Enrollment card shown on this slide: see `enrollment-card.md`. Print it **with** the arm C (OpenRouter) line, because the live demo runs arm C. The card's own printing note still says arm B and is out of date.
