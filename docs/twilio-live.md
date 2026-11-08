# Twilio live setup (#29, #78, PRD §19.3, §19.7)

```
Twilio --POST /sms/inbound, /sms/status (X-Twilio-Signature)--> cloudflared tunnel --> app on 127.0.0.1:8000
app --messages.create (status_callback = PUBLIC_BASE_URL/sms/status)--> Twilio --> phone
```

## 1. Twilio account (human)
- Upgrade the account: a trial has no number of its own and only sends Twilio's canned bodies, not our
  templates (issue #1 LEARN). US SMS also needs 10DLC or toll-free registration, which takes days.
  Without it, demo on the simulated phone and say "SMS simulated" in the pitch.
- Buy an SMS-capable US number. Fill `.env`: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`,
  `DEMO_PHONE`, `SPARE_PHONE` (E.164), `CONSENT_SALT`, `OPERATOR_PASSWORD`, `SESSION_SECRET`.
- Install `cloudflared` (`~/.local/bin` is fine).

## 2. Start the stack
```bash
make demo-up        # = scripts/demo_up
```
- Empty `CLOUDFLARED_TUNNEL`: quick tunnel. Its random `https://*.trycloudflare.com` URL is written to
  `.env` as `PUBLIC_BASE_URL` on every start, so restart = new URL (the webhook is rewritten too).
- `CLOUDFLARED_TUNNEL=<name>`: named tunnel (`cloudflared tunnel login`, `create <name>`,
  `route dns <name> <host>`, once). Set `PUBLIC_BASE_URL=https://<host>` by hand.
- Then it runs the app on 127.0.0.1:8000 with `.env` loaded, waits for `/health`, and sets the `TWILIO_FROM`
  number's "A message comes in" webhook to `POST $PUBLIC_BASE_URL/sms/inbound`. Ctrl-C stops app and tunnel.
  The webhook step is skipped when the Twilio vars are unset (simulated SMS only).

## 3. What the tunnel exposes
- Only `/sms/inbound`, `/sms/status` and `/health`. Every other path that arrives through Cloudflare
  (it carries `Cf-Connecting-Ip`) gets 404, so the operator login, console API and event stream stay local.
- `/sms/inbound` and `/sms/status` check `X-Twilio-Signature` against `PUBLIC_BASE_URL` + path and fail
  closed (403) when `TWILIO_AUTH_TOKEN` or `PUBLIC_BASE_URL` is unset. `PUBLIC_BASE_URL` must match the
  tunnel exactly, or every webhook is rejected.
- `/sms/inbound` only acts on texts whose `From` is `DEMO_PHONE` or `SPARE_PHONE` (digits compared) and
  replies to that configured number; any other sender is ignored. MessageSids are deduped in SQLite.
  A processing failure returns 5xx and is not marked seen, so a Twilio retry is processed.

## 4. Enroll phones
Text `YES` (or `START`) from `DEMO_PHONE` and `SPARE_PHONE` to `TWILIO_FROM` while the stack is up.
After `STOP`, Twilio blocks further sends and sends its own confirmation, so the app sends no R-STOP in real mode.

## 5. Before judging
`scripts/preflight` checks the tunnel, the webhook, both phones opted in, one real SMS (waits for
`delivered`), and a HELP reply from `DEMO_PHONE` reaching the app. `--no-sms` skips both texts.

## 6. Data that leaves the laptop
- Alert and reply texts go to Twilio (template text only, never call content).
- Arm C (`INTENT_MODEL=on` + `TYPESAFE_API_KEY`) sends each caller turn plus the 3 turns before it to
  api.typesafe.ai. Leave it off for any real call; the enrollment card says so when it is on.
