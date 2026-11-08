# CallSafe (Devpost draft)

**Tagline:** We don't ask you to trust AI. We tell you what the caller just asked for, give one step that's safe even if we're wrong, and teach you the trick so you catch it next time, on any phone.

## Problem
Caller-ID and spam filters judge the number, not the conversation. A scam call that gets through still has to ask for something: a one-time code, a payment, or access to your device. That request is the moment of harm, and today nothing on an ordinary phone speaks up when it happens.

## What it does
For subscribers who opt in by text, CallSafe follows the call's transcript. When the caller asks for a code, money or remote access, it sends one SMS that names the request and gives one safe step, for example: "caller is asking for a code. Don't share it. Hang up, call your bank's number yourself." After the call, a follow-up text explains the trick. Replies drive the loop: WRONG is counted toward a human-reviewed, tested policy change; SHARED returns recovery steps; STOP ends it. The texts only ever say stop and check, so a scammer copying them gives safe advice. An operator console shows the live transcript, why each alert fired (by rule ID), the WRONG counter and evaluation results. Silence is never presented as a safety verdict.

## How we built it
- FastAPI backend, single process, asyncio pipeline with an SSE event hub
- faster-whisper `small.en` on CPU for speech-to-text, with a labelled cached-transcript fallback
- Pure-Python rules: a keyword baseline (K) and context rules (B) that check who is speaking, the direction of the request and negation ("don't share it"). The demo runs C when the model is on.
- Optional arm C: the same rules plus Perplexity Decider V1.2, a decision model, through OpenRouter. Opt-in; it sends each caller turn and up to three turns before it to OpenRouter, and any API failure falls back to B for that turn
- Twilio Programmable Messaging behind an `SmsGateway` interface (webhooks check Twilio's signature and fail closed), plus a simulated gateway the operator can switch to
- SQLite holding consent (HMAC hashes of numbers) and counts only; no audio, transcripts or raw numbers stored, and call text is dropped from memory when the call ends
- React + TypeScript + Vite operator console
- Demo call voices generated offline with Qwen3-TTS (synthetic voices)
- Evaluation: a 40-call dev set for tuning, 60 held-out scripted calls (H1) written by an AI agent in a separate context that never saw the rules, the rule tests or any results, then three larger blind sets (594, 1990 and 6228 calls) written by isolated AI agents with no repo access. The held-out sets were sealed by hash before scoring.

## Results
All numbers are scored on AI-written scripted transcripts, not ASR and not real calls, so we make no production claim. On the largest blind set (H4: 6228 calls, 3117 scams and 3111 harmless calls), the keyword baseline caught 2629 of 3117 scams (84.3%, 95% CI 83.0% to 85.6%) but alerted on 2001 of 3111 harmless calls (64.4%). CallSafe's rules (B) caught 2056 of 3117 (65.9%, 95% CI 64.2% to 67.7%) with 27 of 3111 false alerts (0.9%, 95% CI 0.5% to 1.3%). Arm C caught 3094 of 3117 (99.2%) with 9 of 3111 false alerts (0.3%), measured on the branch before it merged, measured with TypeSafe Jev 1.14, the previous arm C model; not yet re-measured with Decider V1.2. On H1 (60 calls; we read these transcripts while diagnosing, so they're no longer fully blind), keywords caught 27 of 30 with 13 of 22 false alerts on hard-benign calls, and B caught 18 of 30 with 0 of 22; paired, we call no win. On the dev set the rules were tuned on, B catches 20 of 20 with no false alerts. B still misses about a third of blind scams; arm C closes most of that gap, at the cost of sending call text off the machine.

## What's honest about the demo
- The call is **real**: a judge dials a Twilio number we own, Twilio forwards it to the subscriber's phone and streams both sides' audio to the laptop. It is not a carrier integration. Fallbacks, said out loud: a two-person conversation on the laptop mic, then a recorded replay.
- Alert texts are **sent through Twilio for real, but US carriers block them** (Twilio error 30034) until our number's 10DLC registration is done. The console mirrors every text and shows the status Twilio reports; we never claim a text arrived.
- The demo runs arm C, so each caller turn and up to three turns before it go to OpenRouter. Speech-to-text stays on the laptop.
- Accuracy numbers come from scripted transcripts, not speech recognition.

## Challenges
- Telling "never share this code" apart from "read me the code": the words match, but the direction of the request is opposite.
- Keeping the advice safe even when we're wrong, and never telling anyone a call is safe.
- Keeping the evaluation honest: the held-out sets are written blind, sealed by hash, and reported with denominators and confidence intervals.
- faster-whisper's `transcribe` returns a lazy generator, so decoding happened inside the event loop until we consumed it in a worker thread.
- A `data/` ignore rule silently dropped a test audio fixture.
- Windows timers wake up to about 15 ms early, which made a real-time replay test flaky.
- Windows line-ending conversion changed the bytes of the sealed held-out files; we store them as single-line JSON so the seal hash matches on every machine.

## What's next
- Carrier routing on the Live Translation (*87) path, so it works on any phone
- An in-call audio prompt
- A consent gate, with caller notice in all-party-consent states
- Sender verification for alert texts
- Real SMS: an upgraded Twilio account with a registered number (10DLC or toll-free)
- Closing B's gap on new wording without sending call text off the machine
