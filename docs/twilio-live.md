# Twilio live setup (#29, PRD §19.3, §19.7)

## 1. Twilio account (human)
- Upgrade the account, or confirm texts carry no "Sent from your Twilio trial account" prefix (§19.5).
  `scripts/sms_kill_check.py` warns if the account is still a trial.
- Buy an SMS-capable US number. Fill `.env`: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`,
  `DEMO_PHONE`, `SPARE_PHONE` (E.164), `CONSENT_SALT`, `OPERATOR_PASSWORD`, `SESSION_SECRET`.

## 2. Start the stack
```bash
make demo-up        # = scripts/demo_up
```
- Empty `CLOUDFLARED_TUNNEL`: quick tunnel. Its random `https://*.trycloudflare.com` URL is written to
  `.env` as `PUBLIC_BASE_URL` on every start, so restart = new URL (the webhook is rewritten too).
- `CLOUDFLARED_TUNNEL=<name>`: named tunnel (`cloudflared tunnel login`, `create <name>`,
  `route dns <name> <host>`, once). Set `PUBLIC_BASE_URL=https://<host>` by hand.
- Then it sets the `TWILIO_FROM` number's "A message comes in" webhook to `POST $PUBLIC_BASE_URL/sms/inbound`
  and runs the app on :8000 with `.env` loaded. Ctrl-C stops app and tunnel.
- `PUBLIC_BASE_URL` must match the tunnel exactly: `/sms/inbound` and `/sms/status` reject any request whose
  Twilio signature was computed for another URL (403).

## 3. Enroll phones
Text `YES` (or `START`) from `DEMO_PHONE` and `SPARE_PHONE` to `TWILIO_FROM` while the stack is up.

## 4. H+1 kill check (§19.7)
```bash
env -u PYTHONPATH -u VIRTUAL_ENV uv run python scripts/sms_kill_check.py   # 10 texts, then reply WRONG
```
Run it with the app stopped (otherwise the app answers the reply, harmlessly). It prints a `LEARN` line with
the delivery median/worst and segment counts; post it on issue #1. If it fails, demo on `SimulatedGateway`
and say so in the pitch.

## 5. Before judging
`scripts/preflight` checks the tunnel, webhook, both phones opted in, and one real SMS.
