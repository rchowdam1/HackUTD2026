# Enrollment invite

The operator texts the ENROLL invite to the demo or spare phone, chosen by name so no number crosses the API. The phone's consent becomes `invited` until it replies YES. Only salted hashes of numbers are stored.

## Sub-features

- `invite.demo-and-spare` sends ENROLL to the spare and the demo phone, marks each `invited` under its own salted hash, rejects unknown names, and leaves no raw number in the database.

## How to get to it (user POV)

- `POST /sms/invite {"phone": "demo"|"spare"}` (cookie required). The console has no button for it; the team calls it from a shell before judging.

## Driving it with verify.py

Preconditions:

- Profile `cached`. Sandbox `DEMO_PHONE=+15550100001`, `SPARE_PHONE=+15550100002` (fictional), simulated SMS mode.

- **Spare, then demo.** For each: `POST /sms/invite`. 200 with a `message_id`; SSE `sms` event for that id with `template_id ENROLL`, status `queued`; outbox last has that id and the ENROLL text from `templates.yaml`; SQLite row for `sha256(CONSENT_SALT + phone)` is `invited`.
- **Unknown name.** `POST /sms/invite {"phone": "other"}` returns 422.
- **Restore.** Reply YES via `POST /sms/simulate-inbound`; demo consent `active` (SQLite).
- **No raw numbers.** The raw bytes of `data/safesignal.db` contain neither number's digits (UTF-8 or UTF-16).
- **Proof.** Assertions in `report.json`.

## Gotchas

- Inviting the demo phone downgrades an active phone to `invited`, which silently stops alerts. The check restores it; a manual run must too.
- A missing `SPARE_PHONE` returns 400 `SPARE_PHONE is not set`; the sandbox always sets both.
- In real mode this texts a real phone. Never call it against a configured Twilio account from automation.
