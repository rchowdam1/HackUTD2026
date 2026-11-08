# Call controls

The operator can cut a replay short with End call, wipe the screen and cancel everything pending with Reset (consent and counts survive), and flip SMS delivery between real (Twilio) and the simulated phone.

## Sub-features

- `controls.end-call-midway` ends a bank replay after its first turn: no further segments, no alert, "call ended".
- `controls.reset-midway` resets a bank replay after turn 2: no late events or SMS from that call (generation invariant), transcript cleared, consent and reply counts unchanged in SQLite.
- `controls.sms-mode-toggle` switches to real (phone frame stays, tagged `real SMS`; next call starts in real mode) and back to simulated.
- `controls.sms-mode-after-reload` reloads the console while the backend is in real mode and expects the toggle to still show real.

## How to get to it (user POV)

- Console buttons `End call`, `Reset`, and the `SMS mode` toggle buttons `real` / `simulated`.
- `POST /demo/end-call`, `POST /demo/reset`, `POST /demo/sms-mode {"mode": "real"|"simulated"}` (cookie required).

## Driving it with verify.py

Preconditions:

- Profile `cached` with the console; demo phone opted in (the checks reply YES if needed).

- **End call.** Click `Run bank`, wait for the first `segment` event, click `End call`. SSE `session finished` for that call within 10 s. Wait until 24 s after start: no event for that `session_ref` after `finished`, fewer than 4 segments, no `decision`/`sms`, outbox unchanged. Banner `call ended`; Why panel `No alert detected`.
- **Reset.** Snapshot SQLite `consent` and `reply_counts`. Click `Run bank`, wait for segment 2, click `Reset`. SSE `session reset`; banner `reset`; `Live transcript` shows `No call yet.`. Wait until 10 s after start (past the OTP turn at ≈5.3 s and the replay end at ≈8 s): no event carrying the old `session_ref` after the reset event, outbox unchanged, both SQLite tables byte-identical to the snapshot.
- **SMS mode.** Click `real`: `POST /demo/sms-mode` → 200, the `Phone` card stays with the tag `real SMS`, `real` has class `on`. Click `Run clinic`: the SSE `session running` payload says `sms_mode: real`; click `Reset`. Click `simulated`: phone card visible, `simulated` has class `on`, the next `Run clinic` starts with `sms_mode: simulated`; `Reset`.
- **Mode after reload.** Click `real`, reload the console, expect `real` to keep class `on` within 5 s. Afterwards the check sets simulated via the API.
- **Proof.** `screenshots/controls.*`, `events-cached.jsonl`.

## Gotchas

- Real mode is safe to toggle in the sandbox: there is no Twilio account (sends fail closed), the clinic call never alerts, and each real-mode call is reset immediately. Never run the bank call in real mode against a configured Twilio account.
- On every (re)connect the console loads `GET /state`, which carries the backend's SMS mode, so `controls.sms-mode-after-reload` holds after a reload (the #64 gap is fixed; the check no longer carries `known_gap`). In real mode the Phone card mirrors every text sent through Twilio with its status (e.g. `Not delivered: carrier blocked (Twilio 30034, …)`), and its reply keys go through the real gateway, so never press them against a configured Twilio account.
- End call and Reset both cancel the replay task; Reset additionally invalidates the generation so late SMS tasks drop. Only Reset clears the transcript.
- Reset emits `session reset` with the old `session_ref` (or null when idle). Filter late events by events *after* the reset event.
- Not yet covered by a check: End call *after* the alert (≈5.3 s into the bank call) still sends the follow-up before `finished`; Run during a live call finishes the old session first; unknown scenario ids return 404.
