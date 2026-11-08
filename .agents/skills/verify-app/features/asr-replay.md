# ASR replay

With `REPLAY_SOURCE=asr` (the demo setting) the bank and clinic replays transcribe the demo WAVs in `audio/demo/<id>/` with faster-whisper `small.en` on CPU instead of reading the cached transcript. The transcript is then not labelled "cached transcript", and the bank call must still raise ALERT-OTP-01 from the transcribed words. If the model can't load, the app silently falls back to the cached transcript.

## Sub-features

- `asr.bank-replay` replays the bank call through whisper: every segment has `source: asr`, ALERT-OTP-01 fires, and the console shows the ASR text without the cached label.

## How to get to it (user POV)

- Start the app with `REPLAY_SOURCE=asr` (`scripts/demo_up` on the demo laptop) and click `Run bank` / `Run clinic`.

## Driving it with verify.py

Preconditions:

- `faster-whisper small.en` cached under `HF_HOME` (default `~/.cache/huggingface`; override with `VERIFY_HF_HOME`). Missing → BLOCKED, never a pass.
- The harness launches a separate instance with profile `asr` (`HF_HUB_OFFLINE=1`): `make verify ARGS="--features asr-replay"`.

- **Run.** Reset, ensure opt-in, open the console, click `Run bank`; wait up to 120 s for `session finished`.
- **Source.** Every SSE segment has `source: asr`. A cached fallback FAILs with the backend log's "ASR unavailable" line as the observed reason.
- **Decision.** Exactly one decision, ALERT-OTP-01.
- **Console.** `Live transcript` has no `cached transcript` tag and contains the first ASR segment's text.
- **Proof.** `artifacts/asr.bank-replay--asr-segments.json`, `screenshots/asr.bank-replay--asr-finished.png`, `backend-asr.log`.

## Gotchas

- The fallback to cached is silent in the UI apart from the tag; always assert `source`, never just "a transcript appeared".
- Model preload happens at startup, so the asr instance takes a few seconds longer to answer `/health`.
- Whisper output is not byte-stable across model or library versions; assert the decision and the source, not exact text.
