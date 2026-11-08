# SMS replies

The subscriber answers texts with keywords. In simulated mode the console's phone frame has YES / WRONG / SHARED / STOP buttons that go through the same inbound handler as Twilio. YES opts in, STOP opts out (and stops alerts), WRONG is counted against the latest alert (SQLite and `GET /aggregates`; the console shows the reply bubble, no counter), SHARED gets category-specific advice, anything else gets HELP. Keywords are trimmed, de-punctuated and case-insensitive.

## Sub-features

- `replies.opt-in-yes` moves consent from stopped to active and answers R-YES.
- `replies.wrong-counter` counts WRONG against ALERT-OTP-01 in SQLite and `/aggregates`, answers R-WRONG, and shows the reply bubble.
- `replies.shared` answers SHARED with R-SHARED-OTP for an OTP alert.
- `replies.keyword-normalise` maps "  wrong. ", "Hello?", "Stop please!", "yes" to WRONG, HELP, STOP, YES.
- `replies.stop-blocks-alerts` shows that after STOP the rules still decide but the alert is skipped, not failed: no sms event, no follow-up, nothing on the phone, Why panel "Monitoring opt-in: No. No text sent".

## How to get to it (user POV)

- Phone frame buttons `YES`, `WRONG`, `SHARED`, `STOP` (visible only in simulated SMS mode).
- `POST /sms/simulate-inbound {"body": "..."}` (cookie required), the endpoint the buttons call.
- A real phone texting the Twilio number (see `twilio-webhooks.md`; real phone is external).

## Driving it with verify.py

Preconditions:

- Profile `cached` with the console. `replies.wrong-counter` and `replies.shared` require `replay.bank-alert` to PASS earlier in the same run (the harness adds it automatically); without an alerted session, replies are not counted.

- **YES.** Reply STOP via the API (so a transition is observable), open the console, click `YES` in the `Phone` card. SSE `reply` keyword YES and `consent` state active; SQLite row for `HMAC-SHA256(CONSENT_SALT, "consent-phone:" + DEMO_PHONE)` is `active`; outbox last is R-YES; phone shows the R-YES text.
- **WRONG.** Read the stored WRONG total n from SQLite. Click `WRONG`. SSE `reply` = `{keyword: WRONG, counted: true, wrong_count: n+1}`; SQLite total n+1 with a row for template ALERT-OTP-01; `GET /aggregates` agrees; outbox last is R-WRONG; the `Phone` card's last incoming bubble is `WRONG`.
- **SHARED.** Click `SHARED`. Reply SHARED counted; outbox last R-SHARED-OTP; phone shows its text.
- **Normalisation.** `POST /sms/simulate-inbound` with each body above; response keyword and outbox template match; the STOP variant writes `stopped`, the final YES writes `active` (SQLite).
- **STOP blocks alerts.** Click `STOP` (SSE consent stopped, SQLite stopped, outbox R-STOP), click `Run bank`, wait for `session finished`. SSE has decision ALERT-OTP-01 and no sms event; outbox unchanged; `Why this alert` shows `Caller asked for a code` and `Monitoring opt-in: No. No text sent`; `main` contains no "failed"; `Phone` shows `Call monitoring is off.`; no transcript marker. Click `YES` to restore; SQLite active.
- **Proof.** `screenshots/replies.*`, SQLite assertions in `report.json`, `events-cached.jsonl`.

## Gotchas

- `counted` is false until this process has successfully sent an alert to the replying phone (`_last_alerts`, per recipient, recorded only after the gateway accepted it); a fresh instance counts nothing, and replies from a phone that got no alert are not counted. That is why two checks require `replay.bank-alert`.
- Reset never clears `_last_alerts`, consent or counts; replies after a reset still attach to the last alert.
- The phone frame bubble list is cleared on each `session running`/`reset`; assert texts after the action, not history.
- Consent events are only emitted on a change; YES while already active emits a `reply` but no `consent` event.
- In real mode a STOP gets no R-STOP from us (Twilio answers); only the simulated phone shows R-STOP.
- Every keyword (not just WRONG) is counted in `reply_counts` once an alert exists; SHARED before any alert becomes HELP. START behaves like YES.
