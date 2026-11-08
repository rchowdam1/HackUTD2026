# Call replay

The operator replays one of two demo calls through the live pipeline. The clinic call mentions a code but tells the listener not to share it: the phone stays silent and the Why panel says "No alert - not a safety verdict". The bank call turns into a request for a code: the rules fire ALERT-OTP-01, the phone gets the alert, the call ends automatically after the last turn, and exactly one follow-up (FU-OTP-01) arrives.

## Sub-features

- `replay.clinic-silent` replays the clinic call: cached transcript shown and labelled, no decision, no SMS, "call ended", "No alert - not a safety verdict".
- `replay.bank-alert` replays the bank call: ALERT-OTP-01 then exactly one FU-OTP-01, auto end-call, and a Why panel that matches the decision.

## How to get to it (user POV)

- Console buttons `Run clinic` and `Run bank` (log in first).
- `POST /demo/run/clinic` or `POST /demo/run/bank` (cookie required) returns 202 and starts a background replay.

## Driving it with verify.py

Preconditions:

- Instance launched with profile `cached` and the console (`make verify ARGS="--features call-replay"`).
- For the bank call the demo phone is opted in; the check replies YES itself if SQLite says otherwise.

- **Clinic.** `POST /demo/reset`, open the console, click `Run clinic`. SSE shows `session running` (arm B, simulated), segments 1-3 equal to `scenarios/demo/clinic/transcript.json` with `source: cached`, then `session finished`; no `decision` or `sms` event; `GET /sms/outbox` length unchanged. The `Live transcript` card shows all three turns and the `cached transcript` tag; banner shows `call ended`; `Why this alert` shows `No alert - not a safety verdict`; `Phone` shows `No texts yet.`.
- **Bank.** Reset, ensure opt-in, open the console, click `Run bank`. SSE: one `decision` with `template_id ALERT-OTP-01`, `followup_template_id FU-OTP-01`; ordered `session running → sms ALERT-OTP-01 → sms FU-OTP-01 → session finished`; both sms events `queued` with message ids; the decision `basis` is a subset of published risk-event `rule_id`s with category `otp`. Outbox gains exactly ALERT-OTP-01 then FU-OTP-01, texts equal to `policy/v1.0/templates.yaml`, ids equal to the SSE ids.
- **Why panel.** In `Why this alert`: headline `Caller asked for a code`; `Rule` = `basis` joined by ", "; `Confidence` = the cited risk event's class in words; `Keyword-only would have fired` = Yes/No from `keyword_arm_would_fire`; `Policy` = `v1.0`.
- **Proof.** `screenshots/replay.*--*-finished.png` + `.aria.txt`, `artifacts/replay.bank-alert--event-order.json`, `artifacts/replay.bank-alert--outbox-new.json`, and the run's `events-cached.jsonl`.

## Gotchas

- Every journey starts from `ctx.api_reset()`, which also sets SMS mode to simulated: reset never changes the mode, and a leftover real mode would hide the phone frame.
- Replays run in real time (clinic ≈14 s, bank ≈22 s). Wait for the `session finished` event, not a sleep.
- Open the console before clicking Run: the reducer clears on `session running`, so a page loaded mid-call shows a partial transcript.
- The follow-up is only sent if consent is still active when the call finishes; a STOP during the call suppresses it by design.
- Starting a replay finishes the previous session first (a follow-up can be sent for it). Reset before each replay for a clean event window.
- The cached transcript texts are the contract here. With `REPLAY_SOURCE=asr` the text comes from whisper; that is `asr-replay`, not this feature.
