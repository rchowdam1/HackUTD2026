# CallSafe (Devpost draft)

**Tagline:** We don't ask you to trust AI. We tell you what the caller just asked for, give one step that's safe even if we're wrong, and teach you the trick so you catch it next time, on any phone.

## Problem
Caller-ID and spam filters judge the number, not the conversation. A scam call that gets through still has to ask for something: a one-time code, a payment, or access to your device. That request is the moment of harm, and today nothing on an ordinary phone speaks up when it happens.

## What it does
For subscribers who opt in by text, CallSafe follows the call's transcript. When the caller asks for a code, money or remote access, it sends one SMS that names the request and gives one safe step, for example: "caller is asking for a code. Don't share it. Hang up, call your bank's number yourself." After the call, a follow-up text explains the trick. Replies drive the loop: WRONG is counted toward a human-reviewed, tested policy change; SHARED returns recovery steps; STOP ends it. The texts only ever say stop and check, so a scammer copying them gives safe advice. An operator console shows the live transcript, why each alert fired (by rule ID), the WRONG counter and evaluation results. Silence is never presented as a safety verdict.

## How we built it
- FastAPI backend, single process, asyncio pipeline with an SSE event hub
- faster-whisper `small.en` on CPU for speech-to-text, with a labelled cached-transcript fallback
- Pure-Python rules: a keyword baseline (K) and context rules (B) that check who is speaking, the direction of the request and negation ("don't share it")
- Twilio Programmable Messaging behind an `SmsGateway` interface, plus a simulated gateway the operator can switch to
- SQLite holding consent (salted hashes of numbers) and counts only; no audio, transcripts or raw numbers stored
- React + TypeScript + Vite operator console
- Demo call voices generated offline with Qwen3-TTS (synthetic voices)
- Evaluation: a 40-call dev set for tuning, and 60 held-out scripted calls (H1) written by an AI agent in a separate context that never saw the rules, the rule tests or any results, sealed by hash before scoring

## Results
On H1 (60 scripted calls, scored on scripted transcripts rather than ASR): keyword baseline caught 9 of 30 scams (30.0%, 95% CI 16.6% to 47.9%) with 6 of 22 false alerts on hard-benign calls; CallSafe's rules caught 5 of 30 (16.6%, 95% CI 7.3% to 33.6%) with 0 of 22 false alerts (upper bound 14.9%); adding the intent model caught 5 of 30 with 1 of 22. Paired, 4 calls were right only under keywords and 6 only under our rules, so we call no win. The same rules catch 19 of 20 scams on the dev set they were tuned on: they don't yet generalise to new wording, and closing that gap is the main open problem. This sample is too small for a production claim.

## What's honest about the demo
- Calls are **replayed** recordings, not live phone calls.
- The carrier signal and routing are **mocked**; this is not a carrier integration.
- SMS is [real, via Twilio to a team phone | simulated in the console]. [Pick one at submission.]
- Accuracy numbers come from scripted transcripts, not speech recognition.

## Challenges
- Telling "never share this code" apart from "read me the code": the words match, but the direction of the request is opposite.
- Keeping the advice safe even when we're wrong, and never telling anyone a call is safe.
- Keeping the evaluation honest: the held-out set is written blind, sealed by hash, and reported with denominators and confidence intervals.
- faster-whisper's `transcribe` returns a lazy generator, so decoding happened inside the event loop until we consumed it in a worker thread.
- A `data/` ignore rule silently dropped a test audio fixture.
- Windows timers wake up to about 15 ms early, which made a real-time replay test flaky.
- Windows line-ending conversion changed the bytes of the sealed held-out files; we store them as single-line JSON so the seal hash matches on every machine.

## What's next
- Carrier routing on the Live Translation (*87) path, so it works on any phone
- An in-call audio prompt
- A consent gate, with caller notice in all-party-consent states
- Sender verification for alert texts
- A fresh held-out set (H2) and an intent model checked against the rules
