# Live mic

Two people take turns talking into the console's microphone on one laptop. The operator clicks `Start live conversation`; `Caller` and `You` buttons appear; tapping one records a turn (the other is disabled) and tapping it again sends the clip, which whisper transcribes in memory into one transcript line for that speaker. An alert does not end the conversation: the alert text goes out and the Why panel fills in while both buttons stay usable. `End call` ends it, and only then does the follow-up text go out. The transcript card shows a `Live mic` tag.

## Sub-features

- `live.api-turns` posts the five bank WAVs as turns: one `asr` segment per turn with the sent speaker, ALERT-OTP-01 mid-conversation, no finish until End call, then exactly the follow-up.
- `live.mic-ui` drives the buttons with Chromium's fake mic: Start, Caller (You disabled), stop, the spoken code request alerts, the call keeps running, End call sends the follow-up and removes the buttons.

## How to get to it (user POV)

- Console button `Start live conversation` (log in first; the browser asks for mic access, allowed on `localhost`), then `Caller` / `You`, then `End call`.
- `POST /live/start`, then `POST /live/utterance` (multipart: `speaker` = `caller` | `subscriber`, `audio` = the clip), then `POST /demo/end-call` (cookie required).

## Driving it with verify.py

Preconditions:

- Profile `asr` (whisper `small.en` cached under `HF_HOME`; missing is BLOCKED): `make verify ARGS="--features live-mic"`.
- Demo phone opted in (`ctx.ensure_opted_in()`), otherwise alerts are skipped by design.

- **API turns.** Reset, `POST /live/start` -> 200 with `session_ref`; post `audio/demo/bank/t01..t05.wav` with the speakers from `scenarios/demo/bank.json`, each -> 200 with non-empty `text`. SSE: segments 1-5 `source: asr` with those speakers, one `decision` ALERT-OTP-01, no `session finished`. `POST /demo/end-call`: order `running -> sms ALERT-OTP-01 -> sms FU-OTP-01 -> finished`; outbox gains exactly those two.
- **Buttons.** Open the console, click `Start live conversation`, wait for `session running`; click `Caller` (`You` is disabled), let the fake mic play for 5 s, click `Caller - tap to stop`. SSE: a caller `asr` segment containing "code", then ALERT-OTP-01. Console: `Live mic` tag, the line in `Live transcript`, Why headline `Caller asked for a code`, `You` enabled again. Click `End call`: markers `* Alert message sent to user` then `* Follow-up message sent to user`; no `Caller` button.
- **Proof.** `artifacts/live.api-turns--live-segments.json`, `artifacts/live.api-turns--event-order.json`, `artifacts/live.mic-ui--mic-segment.json`, `screenshots/live.mic-ui--alert-mid-call.png`, `screenshots/live.mic-ui--ended.png`.

## Gotchas

- The fake mic loops `bank/t04.wav` for the whole browser, and Chromium only reads the file at launch: the harness passes it in `context.py`.
- The 5 s in `live.mic-ui` is the length of the spoken turn, not a wait on the app; everything after it waits on SSE events.
- Whisper text is not byte-stable; assert speaker, source and the decision, and only that "code" appears.
- A turn that transcribes to nothing (silence) adds no line; a turn posted after End call gets 409.
