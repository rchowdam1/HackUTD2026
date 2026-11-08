# Twilio webhooks

Twilio posts inbound texts to `/sms/inbound` and delivery updates to `/sms/status`. Both are authenticated by `X-Twilio-Signature` computed over `PUBLIC_BASE_URL + path` and the form fields; unsigned or mis-signed requests get 403, and both fail closed when `TWILIO_AUTH_TOKEN` or `PUBLIC_BASE_URL` is unset. Only texts from `DEMO_PHONE` / `SPARE_PHONE` are handled; any other `From` is dropped with empty TwiML. Inbound replies are deduplicated by `MessageSid`; status callbacks for messages we sent become `sms` events (`undelivered` reads as `failed`).

## Sub-features

- `webhooks.signature-required` rejects unsigned and mis-signed inbound and status posts with 403, drops a signed STOP from a missing or unenrolled sender, and changes nothing.
- `webhooks.signed-inbound-dedupe` accepts a correctly signed "Wrong." (empty TwiML, WRONG reply, counted once) and ignores a repeat of the same MessageSid.
- `webhooks.status-callback` relays `delivered` and `undelivered` for a known message id and ignores unknown ids.

## How to get to it (user POV)

- A real phone texts the Twilio number; Twilio calls `POST {PUBLIC_BASE_URL}/sms/inbound` (form-encoded `MessageSid`, `Body`, `From`).
- Twilio reports delivery on `POST {PUBLIC_BASE_URL}/sms/status` (`MessageSid`, `MessageStatus`).

## Driving it with verify.py

Preconditions:

- Profile `cached`. The sandbox sets `TWILIO_AUTH_TOKEN` (signing only) and `PUBLIC_BASE_URL=http://127.0.0.1:<port>`; the harness signs with Twilio's documented algorithm (`twilio_signature` in `checks.py`), independent of the app's Twilio library.

- **Unsigned / bad signature.** Post `{MessageSid, Body: WRONG, From: DEMO_PHONE}` without a signature and with one corrupted character; post `/sms/status` unsigned. All 403. Then post a signed STOP with `From` empty and with an unenrolled number: both 200 empty TwiML. No `reply`/`sms`/`consent` events within 1 s; SQLite WRONG total and demo-phone consent unchanged.
- **Signed inbound.** Post `Body: "Wrong."` signed. 200, `content-type: text/xml`, body contains `<Response></Response>`; SSE `reply` keyword WRONG; SSE `sms` R-WRONG `delivered` (the reply text); SQLite WRONG total +1 when `counted` (always counted once `replay.bank-alert` passed in the run).
- **Dedupe.** Post the identical signed request again. 200; no `reply`/`sms` event within 1.5 s; SQLite unchanged.
- **Status.** Take the newest outbox `message_id`; post signed `MessageStatus=delivered` then `undelivered`. Each 204 with an SSE `sms` event for that id and template, status `delivered` then `failed`. An unknown `MessageSid` returns 204 with no event.
- **Proof.** Assertions in `report.json`, `events-cached.jsonl`.

## Gotchas

- The signature covers the exact URL Twilio called. Behind the tunnel that is the public https URL, which is why `PUBLIC_BASE_URL` must match the tunnel exactly; a mismatch shows up as 403 on every real webhook.
- A duplicate MessageSid still returns 200 so Twilio stops retrying; assert on side effects, not status.
- `webhooks.status-callback` needs at least one message in the outbox; run order puts it after replies. Alone, it is BLOCKED, not passed.
- Real Twilio delivery through the tunnel is external (see `coverage.json`). Through the tunnel, only `/sms/inbound`, `/sms/status` and `/health` answer (requests carrying `Cf-Connecting-Ip` to any other path get 404, `app.main`); unit-tested in `tests/sms`, since the sandbox has no tunnel.
- SHA256 signature settings are not supported (`algorithm` is never passed).
