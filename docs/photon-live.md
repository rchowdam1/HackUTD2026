# Photon live setup (#68, PRD §19.3, §19.7)

Real mode sends iMessage through Photon **Spectrum** (Spectrum Cloud, `app.photon.codes`). Spectrum has no
HTTP send API; only its TypeScript SDK can send. So `hackutd/` is a small Bun bridge that owns the SDK:

```
backend PhotonGateway --POST 127.0.0.1:8787/send {to, text}--> hackutd bridge --spectrum-ts--> iMessage
backend /sms/inbound  <--POST {id, text, sender}--------------- hackutd bridge <--app.messages-- iMessage
```

Both hops carry `x-bridge-token: $PHOTON_BRIDGE_TOKEN`. `/sms/inbound` returns 403 when the token is unset
or wrong. Inbound comes over the SDK's own connection, so messaging needs no public webhook or tunnel, and
nothing on this laptop is published: the app listens on 127.0.0.1 only. Never put a tunnel in front of :8000
(it would expose the operator login and every route); if one is ever needed, gate it with Cloudflare Access.

`/sms/inbound` only acts on texts whose `sender` is `DEMO_PHONE` or `SPARE_PHONE` (digits compared) and
replies to that configured number; a missing or other sender is ignored. So the iMessage handle that texts
the line must be the phone number, not an Apple ID email. Message ids are deduped in SQLite. The bridge
retries a forward until the backend answers 2xx (5xx/unreachable back off up to 30 s), so a STOP sent
while the app restarts arrives late instead of being lost.

## 1. One-time setup (human)
- `hackutd/` was scaffolded with
  `bun create spectrum-project@latest hackutd --projectId <PROJECT_ID> --providers imessage --yes`
  (the project id is on the Photon dashboard; ask Ameya).
  That logs in to Spectrum Cloud and writes `hackutd/.env` (`PROJECT_ID`, `PROJECT_SECRET`; gitignored).
  On a new checkout, copy `hackutd/.env` across or rerun the command, then `cd hackutd && bun install`.
- Root `.env`: set `PHOTON_BRIDGE_TOKEN` to any random string (`openssl rand -hex 16`), plus `DEMO_PHONE`,
  `SPARE_PHONE` (E.164), `PHOTON_LINE` (our Photon line, E.164; ask Ameya, never commit it),
  `CONSENT_SALT`, `OPERATOR_PASSWORD`, `SESSION_SECRET`.
- Free/Pro plans use a shared line pool. Each recipient must be registered as a project user in the Photon
  dashboard first, otherwise sends fail with `Target not allowed for this project`. Register both phones.
  Quotas: 50 new conversations per line per day.

## 2. Start the stack
```bash
make demo-up        # = scripts/demo_up
```
This starts the app on 127.0.0.1:8000, waits for `/health`, then starts the bridge (`bun install && bun start`
in `hackutd/`, skipped when `PHOTON_BRIDGE_TOKEN` is unset). Ctrl-C stops both.
To run the bridge alone: `cd hackutd && PHOTON_BRIDGE_TOKEN=... bun start`
(it reads `hackutd/.env` for the Spectrum credentials).

## 3. Enroll phones
Text `YES` (or `START`) from `DEMO_PHONE` and `SPARE_PHONE` to `PHOTON_LINE` while the stack is up. Then flip
the console's SMS mode to **real**. Photon does no STOP handling of its own, so the app answers STOP with
R-STOP itself. Spectrum sends no delivery receipts, so real-mode alerts stay `queued` in the console.

## 4. Preflight
`scripts/preflight` checks the bridge's `/health` on localhost, sends R-HELP to `DEMO_PHONE` through it
(PASS = the bridge accepted it; Spectrum has no delivery receipts), then waits for you to reply HELP from
`DEMO_PHONE` and for that reply to reach the app. `--no-sms` skips both texts.

## 5. Data that leaves the laptop
- Alert and reply texts go to Photon (template text only, never call content).
- Arm C (`INTENT_MODEL=on` + `TYPESAFE_API_KEY`) sends each caller turn plus the 3 turns before it to
  api.typesafe.ai. Leave it off for any real call; the enrollment card says so when it is on.
