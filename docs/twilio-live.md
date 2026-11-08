# Twilio live setup (#29, #78, #94, PRD §19.3, §19.7)

```
Twilio --POST /sms/inbound, /sms/status (X-Twilio-Signature)--> cloudflared tunnel --> app on 127.0.0.1:8000
app --messages.create (status_callback = PUBLIC_BASE_URL/sms/status)--> Twilio --> phone
phone A --calls--> TWILIO_FROM --POST /voice/incoming--> app: TwiML <Start><Stream both_tracks> + <Dial>DEMO_PHONE
Twilio --wss /voice/stream (mu-law 8 kHz, x-twilio-signature)--> tunnel --> app --> whisper --> pipeline --> console
```

## 1. Twilio account (human)
- Upgrade the account: a trial has no number of its own and can't send our template bodies. US SMS also
  needs 10DLC or toll-free registration, which takes days. Our account is still a trial, so the demo runs
  on the simulated phone; say "SMS simulated" in the pitch.
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
- Only `/sms/inbound`, `/sms/status`, `/voice/incoming`, the `/voice/stream` socket and `/health`. Every other path that arrives through Cloudflare
  (it carries `Cf-Connecting-Ip`) gets 404, so the operator login, console API and event stream stay local.
- `/sms/inbound` and `/sms/status` check `X-Twilio-Signature` against `PUBLIC_BASE_URL` + path and fail
  closed (403) when `TWILIO_AUTH_TOKEN` or `PUBLIC_BASE_URL` is unset. `PUBLIC_BASE_URL` must match the
  tunnel exactly, or every webhook is rejected.
- `/sms/inbound` only acts on texts whose `From` is `DEMO_PHONE` or `SPARE_PHONE` (digits compared) and
  replies to that configured number; any other sender is ignored. MessageSids are deduped in SQLite.
  A processing failure returns 5xx and is not marked seen, so a Twilio retry is processed.
- `/voice/stream` is a WebSocket, which the tunnel's 404 filter (HTTP middleware) never sees, so it checks
  `x-twilio-signature` over `wss://<tunnel host>/voice/stream` itself and refuses the handshake (403) otherwise.

## 4. Enroll phones
Text `YES` (or `START`) from `DEMO_PHONE` and `SPARE_PHONE` to `TWILIO_FROM` while the stack is up.
After `STOP`, Twilio blocks further sends and sends its own confirmation, so the app sends no R-STOP in real mode.

## 5. Live call (#94, optional; replay stays the stage default)
`scripts/demo_up` also points the `TWILIO_FROM` number's "A call comes in" webhook at `POST /voice/incoming`.
Call `TWILIO_FROM` from any phone (phone A, the "scammer"). `DEMO_PHONE` rings, and the two phones talk normally.
The console shows the call as it happens. There's no Run button to press.
- Twilio's inbound track is phone A (labelled caller) and the outbound track is `DEMO_PHONE` (labelled you).
- Each side is cut at a 0.7 s pause (8 s max), transcribed in memory by whisper, and run like a replay (arm B, or arm C with `INTENT_MODEL=on`,
  which sends the call text to OpenRouter: leave it off for a real call, see §7).
  The OTP alert lands about 3 s after the caller finishes asking for the code (`ingest/live.py`).
- Start the stack with `REPLAY_SOURCE=asr` so the model is preloaded; otherwise the first utterance waits for it to load.
- Hanging up ends the session and sends the follow-up. End call / Reset in the console also work.
- If the stream is refused (wrong `PUBLIC_BASE_URL`), the call still connects but nothing is monitored.

## 6. Before judging
`scripts/preflight` checks the tunnel, the webhook, both phones opted in, one real SMS (waits for
`delivered`), and a HELP reply from `DEMO_PHONE` reaching the app. `--no-sms` skips both texts.

## 7. Data that leaves the laptop
- Alert and reply texts go to Twilio (template text only, never call content).
- Live call audio passes through Twilio (it carries the call) to the app. It is transcribed on the laptop and never
  written to disk; the transcript is dropped when the call ends.
- Arm C (`INTENT_MODEL=on` + `OPENROUTER_API_KEY`) sends each caller turn plus up to 3 turns before it to
  OpenRouter, which forwards it to a host of Perplexity Decider V1.2. The app logs a line saying so at startup.
  Leave it off for any real call.
