# Photon live setup (#68, PRD §19.3, §19.7)

Real mode sends iMessage through Photon **Spectrum** (Spectrum Cloud, `app.photon.codes`). Spectrum has no
HTTP send API; only its TypeScript SDK can send. So `hackutd/` is a small Bun bridge that owns the SDK:

```
backend PhotonGateway --POST 127.0.0.1:8787/send {to, text}--> hackutd bridge --spectrum-ts--> iMessage
backend /sms/inbound  <--POST {id, text, sender}--------------- hackutd bridge <--app.messages-- iMessage
```

Both hops carry `x-bridge-token: $PHOTON_BRIDGE_TOKEN`. `/sms/inbound` returns 403 when the token is unset
or wrong. Inbound comes over the SDK's own connection, so messaging needs no public webhook or tunnel.

## 1. One-time setup (human)
- `hackutd/` was scaffolded with
  `bun create spectrum-project@latest hackutd --projectId 35a6c20b-6bdb-4471-a729-53c0159313a1 --providers imessage --yes`.
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
This starts the tunnel, the bridge (`bun install && bun start` in `hackutd/`, skipped when
`PHOTON_BRIDGE_TOKEN` is unset) and the app on :8000. Ctrl-C stops all three.
To run the bridge alone: `cd hackutd && PHOTON_BRIDGE_TOKEN=... bun start`
(it reads `hackutd/.env` for the Spectrum credentials).

## 3. Enroll phones
Text `YES` (or `START`) from `DEMO_PHONE` and `SPARE_PHONE` to `PHOTON_LINE` while the stack is up. Then flip
the console's SMS mode to **real**. Photon does no STOP handling of its own, so the app answers STOP with
R-STOP itself. Spectrum sends no delivery receipts, so real-mode alerts stay `queued` in the console.

## 4. Preflight
The Twilio H+1 kill check is retired. `scripts/preflight` still checks Twilio for the webhook/sms steps,
so those will FAIL until a-preflight ports them (ASK on issue #1).
