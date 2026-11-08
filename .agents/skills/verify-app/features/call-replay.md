# Call replay

The operator replays one of three demo calls through the live pipeline. With `INTENT_MODEL=on` and `OPENROUTER_API_KEY` set the replay runs arm C (rules + Perplexity Decider), otherwise arm B (rules only). The clinic call mentions a code but tells the listener not to share it: the phone stays silent and the Why panel says "No alert detected". The bank call turns into a request for a code: the rules fire ALERT-OTP-01, the phone gets the alert, the call ends automatically after the last turn, and exactly one follow-up (FU-OTP-01) arrives. The grandson call asks for cash with no trigger phrase: the rules miss it, and only the model (arm C) alerts with ALERT-PAY-01.

## Sub-features

- `replay.clinic-silent` replays the clinic call (opted in): cached transcript shown and labelled, no decision, no SMS, no transcript marker, "call ended", "No alert detected".
- `replay.grandson-rules-only` replays the grandson call in the keyless sandbox: arm B, transcript shown, no decision, no SMS, "No alert detected".
- `replay.bank-alert` replays the bank call: ALERT-OTP-01 then exactly one FU-OTP-01, auto end-call, a Why panel that matches the decision, and transcript markers for both texts.

## How to get to it (user POV)

- Console buttons `Run clinic`, `Run bank` and `Run grandson` (log in first).
- `POST /demo/run/clinic`, `/demo/run/bank` or `/demo/run/family` (cookie required) returns 202 and starts a background replay.

## Driving it with verify.py

Preconditions:

- Instance launched with profile `cached` and the console (`make verify ARGS="--features call-replay"`).
- For the bank call the demo phone is opted in; the check replies YES itself if SQLite says otherwise.

- **Clinic.** `POST /demo/reset`, ensure opt-in, open the console, click `Run clinic`. SSE shows `session running` (arm B, simulated; banner `call running · rules only`), segments 1-3 equal to `scenarios/demo/clinic/transcript.json` with `source: cached`, then `session finished`; no `decision` or `sms` event; `GET /sms/outbox` length unchanged. The `Live transcript` card shows all three turns and the `cached transcript` tag; banner shows `call ended`; `Why this alert` shows `No alert detected`; `Phone` shows `No texts yet.`; the transcript has no `p.marker`.
- **Bank.** Reset, ensure opt-in, open the console, click `Run bank`. SSE: one `decision` with `template_id ALERT-OTP-01`, `followup_template_id FU-OTP-01`; ordered `session running → sms ALERT-OTP-01 → sms FU-OTP-01 → session finished`; both sms events `queued` with message ids; the decision `basis` is a subset of published risk-event `rule_id`s with category `otp`. Outbox gains exactly ALERT-OTP-01 then FU-OTP-01, texts equal to `policy/v1.0/templates.yaml`, ids equal to the SSE ids.
- **Why panel.** In `Why this alert`: headline `Caller asked for a code`; `Caller said` = the flagged line (segment `span_seq[-1]` of the cited risk event) in curly quotes, with exactly the words at the event's `match_spans` in `<mark>`; `Why it matters` = the fixed otp sentence; `We texted` = the ALERT-OTP-01 template minus the `CallSafe:` prefix; `Speed` = `Text sent N.NN s after the line came in` (the alert sms event's `latency_ms`; a live call says `after the caller stopped talking`); `Caught by` = `CallSafe rules` (the cited risk event has `source: rule` and `score: null`). A model detection reads `Perplexity Decider: NN.N% sure the caller wants money` (or `a code` / `access to your device`) from the event's `score`, with the whole flagged line highlighted; the keyless sandbox can't produce one.
- **Grandson.** Reset, ensure opt-in, click `Run grandson`. SSE `session running` arm B; segments equal `scenarios/demo/family/transcript.json` (cached); `session finished`; no `decision`; outbox unchanged; `Why this alert` shows `No alert detected`.
- **Transcript markers.** In `Live transcript`, the line right after the flagged line is `p.marker` `→ Alert text sent` (shown upper-case; `delivered` / `not delivered` once a status callback says so); the markers are exactly that and `→ Follow-up text sent` (last, after the call ends).
- **Proof.** `screenshots/replay.*--*-finished.png` + `.aria.txt`, `artifacts/replay.bank-alert--event-order.json`, `artifacts/replay.bank-alert--outbox-new.json`, and the run's `events-cached.jsonl`.

## Gotchas

- Every journey starts from `ctx.api_reset()`, which also sets SMS mode to simulated: reset never changes the mode, and a leftover real mode would hide the phone frame.
- Cached replays with turn audio are paced by it (each line is due at its `t_start_ms`): clinic ≈15 s, bank ≈22 s, grandson ≈29 s. Wait for the `session finished` event, not a sleep.
- Open the console before clicking Run: the reducer clears on `session running`, so a page loaded mid-call shows a partial transcript.
- Markers come from `sms` events (a failed one reads `not delivered`), placed after the transcript line that was last when the event arrived; they are console-only, there is no marker event.
- The follow-up is only sent if consent is still active when the call finishes; a STOP during the call suppresses it by design.
- Starting a replay finishes the previous session first (a follow-up can be sent for it). Reset before each replay for a clean event window.
- The cached transcript texts are the contract here. With `REPLAY_SOURCE=asr` the text comes from whisper; that is `asr-replay`, not this feature.
