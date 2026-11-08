# Bridge inbound

The Photon Spectrum bridge (`hackutd/`, Bun) forwards every inbound iMessage to `POST /sms/inbound` as JSON `{id, text, sender}` with header `x-bridge-token: $PHOTON_BRIDGE_TOKEN`. A missing, empty or wrong token gets 403, and the endpoint fails closed when `PHOTON_BRIDGE_TOKEN` is unset. Accepted texts go through the same keyword handler as the simulated phone, deduplicated by `id`.

## Sub-features

- `webhooks.token-required` rejects posts with no, empty or wrong `x-bridge-token` with 403 and changes nothing.
- `webhooks.inbound-dedupe` accepts "Wrong." with the right token (204, WRONG reply, counted once) and ignores a repeat of the same `id`.

## How to get to it (user POV)

- A real phone texts the Photon line; the bridge reads it from `app.messages` and calls `POST {BACKEND_URL}/sms/inbound`.

## Driving it with verify.py

Preconditions:

- Profile `cached`. The sandbox sets a random `PHOTON_BRIDGE_TOKEN` and `PHOTON_BRIDGE_URL=http://127.0.0.1:9` (discard port), so real-mode sends fail closed and never reach a running bridge. The harness posts exactly what `hackutd/src/index.ts` posts.

- **Bad token.** Post `{id, text: WRONG, sender: DEMO_PHONE}` with no header, an empty token and a token with one changed character. All 403. Then, with the right token, post STOP with `sender: null` and with an unenrolled number: both 204 (dropped, so the bridge doesn't retry). No `reply`/`sms`/`consent` events within 1 s; SQLite WRONG total and demo-phone consent unchanged.
- **Inbound.** Post `text: "Wrong."` with the token. 204; SSE `reply` keyword WRONG; SSE `sms` R-WRONG `delivered` (simulated mode); SQLite WRONG total +1 when `counted` (always counted once `replay.bank-alert` passed in the run).
- **Dedupe.** Post the identical request again. 204; no `reply`/`sms` event within 1.5 s; SQLite unchanged.
- **Proof.** Assertions in `report.json`, `events-cached.jsonl`.

## Gotchas

- A duplicate `id` still returns 204; assert on side effects, not status.
- Spectrum sends no delivery receipts, so there is no status callback route any more (`/sms/status` was removed with Twilio).
- The bridge itself (Spectrum SDK, real iMessage delivery) is external (see `coverage.json`).
