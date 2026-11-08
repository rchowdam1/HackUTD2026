# Photon live setup (#68, PRD §19.3, §19.7)

Real mode sends through Photon's messaging API (`https://api.photon.codes/v1`, Bearer project API key).
The channel is iMessage by default. `PHOTON_PLATFORM=sms` uses the same code path, but Photon SMS needs an
approved US 10DLC campaign, which is the same thing that blocked Twilio. Nothing below has been run against a
live Photon account yet. If a call fails, check it against `https://api.photon.codes/openapi.json`.

## 1. Photon project (human)
- In the Photon dashboard (Beta / 2.0 platform, not Spectrum), create a project and a project API key
  (`pho_sk_...`). Fill `.env`: `PHOTON_API_KEY`, `PHOTON_PROJECT_ID` (`pho_prj_...`), `DEMO_PHONE`, `SPARE_PHONE`
  (E.164), `CONSENT_SALT`, `OPERATOR_PASSWORD`, `SESSION_SECRET`.
- Assign each phone to a shared iMessage line. A shared line only texts a phone that has an active
  assignment and has messaged it since that assignment, so no unsolicited first text:
  ```bash
  H=(-H "Authorization: Bearer $PHOTON_API_KEY" -H "Content-Type: application/json")
  API=https://api.photon.codes/v1/projects/$PHOTON_PROJECT_ID
  curl "${H[@]}" -H "Idempotency-Key: assign-demo" -d "{\"handle\":\"$DEMO_PHONE\"}" $API/platforms/imessage/assignments
  ```
  Repeat with `SPARE_PHONE` and `Idempotency-Key: assign-spare`.
- `PHOTON_SENDER_ID` is our line's agent user (`pho_usr_...`). Find it with
  `curl "${H[@]}" "$API/users?platform=imessage"` and take the item whose `kind` is `agent`.
- Create the webhook destination once. The URL is replaced on every `make demo-up`:
  ```bash
  curl "${H[@]}" -H "Idempotency-Key: safesignal-webhook" -d '{"name":"safe-signal","apiVersion":"2026-07-01",
    "url":"https://example.com/sms/inbound",
    "enabledEvents":["message.received","message.dispatched","message.delivered","message.failed"]}' \
    https://api.photon.codes/v1/projects/$PHOTON_PROJECT_ID/webhooks/destinations
  ```
  Put `destination.id` in `PHOTON_WEBHOOK_ID` and `signingSecret` (`whsec_...`) in `PHOTON_WEBHOOK_SECRET`.
  The secret is shown only on create or rotate.

## 2. Start the stack
```bash
make demo-up        # = scripts/demo_up
```
- Empty `CLOUDFLARED_TUNNEL`: quick tunnel. Its random `https://*.trycloudflare.com` URL is written to `.env`
  as `PUBLIC_BASE_URL` on every start, so a restart gives a new URL (the webhook is repointed too).
- `CLOUDFLARED_TUNNEL=<name>`: named tunnel (`cloudflared tunnel login`, `create <name>`,
  `route dns <name> <host>`, once). Set `PUBLIC_BASE_URL=https://<host>` by hand.
- It then PATCHes the `PHOTON_WEBHOOK_ID` destination to `$PUBLIC_BASE_URL/sms/inbound` and runs the app on
  :8000 with `.env` loaded. Ctrl-C stops the app and the tunnel.
- `/sms/inbound` takes every event and checks the Standard Webhooks signature (`webhook-id`,
  `webhook-timestamp`, `webhook-signature`, 5-minute tolerance). It returns 403 if `PHOTON_WEBHOOK_SECRET` is
  unset or wrong. `message.received` drives keyword replies. `message.dispatched|delivered|failed` become
  `sent|delivered|failed` SMS events.

## 3. Enroll phones
Text `YES` (or `START`) from `DEMO_PHONE` and `SPARE_PHONE` to the assigned line while the stack is up. This
also opens the line for our sends. Photon has no carrier STOP handling, so the app answers STOP with R-STOP
itself.

## 4. Kill check and preflight
`scripts/sms_kill_check.py` and the webhook/sms checks in `scripts/preflight` still call Twilio and will
FAIL until a-preflight ports them (ASK on issue #1). `scripts/preflight --no-sms` is unaffected apart from the
webhook check.
