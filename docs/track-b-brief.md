# Track B agent brief (Phone + operator + voice)

Owner: Ameya (`UnitedDiagram`). Paste this into an agent: "Read `docs/track-b-brief.md`. Your assignment is `b-<name>`."

## Read first
- `PRD.md` §19 is the build spec and wins over every other section. Read §19.1–§19.5, §19.7 and §19.10 in full.
- `AGENTS.md` has the team rules: branches, commits, the board (issue #1) and PRs.
- Read the board before every step (`gh issue view 1 --comments`), especially LEARN posts and anything addressed to your agent name.
- Arnav's skeleton (PR #2) is merged. Read `backend/app/models.py`, `events.py`, `pipeline.py`, `ingest/__init__.py` and the stub in your own package before writing code.

## Ownership
Track B owns `backend/app/{sms,consent,api,storage}/`, `console/`, `voice/`, `audio/`, `.env.example` and the tunnel config. Inside Track B you own only your assignment's paths plus its `tests/<pkg>/` directory.
- **Arnav (Track A) owns, never edit:** `models.py`, `main.py`, `pipeline.py`, `events.py`, `pyproject.toml`, `uv.lock`, `Makefile`, `scripts/`, `policy/`, `backend/app/{ingest,asr,rules,policy,intent}/`, `tests/conftest.py`, `tests/fixtures/`, `tests/contracts/`. Import them. Post an ASK to the owning Track A agent for a change or a Python dependency.
- **Never read or write** `scenarios/H1/`. Never write under `scenarios/`, `eval/` or `results/` (Rithik, Track C).
- `.env.example` already lists every variable name. Don't add values. Post an ASK to `b-brief` if you need a new name.

## How to work
- Branch `UnitedDiagram/b-<name>` in its own worktree from `origin/main`. Push as soon as it exists; commit and push after every small working change.
- Post CLAIM (branch + paths), DONE (PR link + files changed), and LEARN for any Twilio, tunnel or TTS quirk.
- Build exactly to the §19.4 contracts and the B-internal interfaces below. If something is ambiguous, post an ASK; don't guess.
- A PR is mergeable only if `make smoke` passes on your rebased branch. Open with `gh pr create --fill`. Ameya merges at :00 and :30. Never push to `main`.
- Never commit secrets. Credentials and phone numbers live only in `.env`.
- Write the minimum code that meets your "done when".

## B-internal interfaces (mock the other agents' side until it lands)
- `app.consent`: `is_active() -> bool` (keep this name; it exists in the skeleton), `get_state() -> "invited"|"active"|"stopped"`, `set_state(state)`. `set_state` publishes a `consent` event.
- `app.storage`: `init()` (keep this name; `main.py` calls it at startup), `incr_reply(keyword, template_id) -> int` (returns the new count), `aggregates() -> dict`.
- `app.sms`: `get_gateway() -> SmsGateway` (keep; the pipeline calls it), `set_mode("real"|"simulated")`, `get_mode()`. `send()` is synchronous (see `SmsGateway` in `models.py`).
- Auth: b-api exports `require_operator` (a FastAPI dependency) from `app.api.auth`. Other B routers that need operator auth import it.

## Known contract gaps (ASK Arnav before building around them)
- The `sms` event payload has no message text, so the simulated phone frame can't show it. b-sms asks `a-templates` for either a `text` field on `SmsPayload` or a template-text route.
- `counted` in the `reply` payload is undefined. b-sms asks; proposed meaning: false for duplicate `MessageSid` or a reply with no alerted session.

## Assignments (one agent each)

### b-sms: `backend/app/sms/`, `tests/sms/`
Implement `SmsGateway` (§19.3–§19.4):
- `TwilioGateway`: Programmable Messaging. Routers `POST /sms/inbound` and `POST /sms/status` (define `router` in a module; auto-discovered). Validate signatures with Twilio's validator against `PUBLIC_BASE_URL` + path. These routes use the Twilio signature, not the operator cookie.
- `SimulatedGateway`: same interface. Records sent messages for the console phone frame. Add `POST /sms/simulate-inbound` (operator cookie required) so the phone frame's YES/WRONG/SHARED/STOP buttons go through the same inbound handler.
- Runtime toggle via `set_mode` / `get_mode`; `get_gateway()` returns the current one.

`send(template_id, session_ref)` calls `consent.is_active()` first and raises if not active. Text comes from `app.policy.templates.get(id)` (unknown id -> `KeyError`); never hardcode copy. See the `a-templates` FYI on the board (PR #4). The pipeline already emits the `queued` sms event; the gateway emits only `sent|delivered|failed` from status callbacks.

Inbound:
- Deduplicate by `MessageSid`.
- Normalise: trim, strip punctuation, ignore case (`"Wrong."` counts).
- Map exactly per §19.4: STOP variants -> stopped + R-STOP; START/YES -> active + R-YES; SHARED -> `templates.shared_for(<latest session's alert template_id>)`; WRONG -> R-WRONG + `storage.incr_reply`; anything else -> R-HELP.
- Attach replies to the latest session that had an action warning. Track that session ref and its alert template_id inside `app.sms` when an ALERT template is sent; `pipeline.current()` is `None` after reset.
- Publish `sms` and `reply` events through `app.events.emit`.

**Done when** pytest covers every keyword, MessageSid dedupe, signature rejection and consent refusal against mocked Twilio.

### b-consent-storage: `backend/app/consent/`, `backend/app/storage/`, `tests/consent/`, `tests/storage/`
SQLite at `data/safesignal.db` (already gitignored). Store:
- consent: salted SHA-256 (`CONSENT_SALT`) of the E.164 number, plus state `invited|active|stopped`
- reply counts by keyword and template
- aggregates
- policy history

No raw numbers, transcripts or audio. The send-to number comes from `DEMO_PHONE` / `SPARE_PHONE`. Reset never changes consent or aggregates.

**Done when** pytest shows the stored state transitions and that no raw number is ever written to the database.

### b-api: `backend/app/api/`, `tests/api/`
Operator routes (§19.4):
- `POST /login`: compares with `OPERATOR_PASSWORD`, sets a session cookie signed with `SESSION_SECRET`.
- `GET /events/stream`: SSE that subscribes via `app.events.hub.subscribe()`; never consumes the work queue.
- `POST /demo/run/{scenario_id}` -> `app.ingest.run(scenario_id, sms_mode=sms.get_mode())`, started as a background task. `POST /demo/end-call` -> `pipeline.finish(current ref)`. `POST /demo/reset` -> `pipeline.reset()`. `POST /demo/sms-mode` -> `sms.set_mode(...)`.
- `GET /results/latest`: returns `results/latest.json` unchanged, or HTTP 200 `{"status":"pending"}` if missing.
- `GET /aggregates` -> `storage.aggregates()`.

Every route in `app/api/` except `/login` and `/health` requires the cookie.

**Done when** pytest covers auth rejection, the results file (including pending) and the SSE stream relaying a fake event.

### b-console: `console/` (incl. `package.json` + lockfile)
React + TypeScript + Vite, one operator screen. Use a Vite dev proxy to the backend so the cookie and SSE are same-origin.
- login
- large-type live transcript, labelled "cached transcript" when `source` is `cached`
- "Why this alert" panel: rule ID or category, confidence in words, whether keyword-only would have fired, policy version, "no alert - not a safety verdict"
- WRONG counter
- Run-clinic, Run-bank, End call, Reset
- SMS-mode toggle; in simulated mode a phone frame labelled "simulated SMS" with YES/WRONG/SHARED/STOP buttons (`POST /sms/simulate-inbound`)
- results card (handles `pending`)
- "Where we fail" card

Build against `tests/fixtures/events/*.json` until the real stream works.

**Done when** it renders a full fixture replay, readable from 2 m away.

### b-voice: `voice/`, `audio/`
Demo call audio with Qwen3-TTS, offline, dependencies in `voice/requirements.txt` (not the app's). First check the licence, the weights download and generation on our hardware; if any fails, post BLOCKED and fall back to team-recorded voices.
1. Read Rithik's demo scripts in `scenarios/demo/*.json` (read-only).
2. Voice each turn with a distinct caller and subscriber voice.
3. Round-trip each clip through 8 kHz mu-law.
4. Write to `audio/demo/<id>/tNN.wav`, matching each turn's `audio` path.
5. Print each clip's duration and post them as a REPLY to Rithik's demo-scenario agent, so the cached `transcript.json` timings match the audio.

Limits: clinic audio <= 15 s, bank audio <= 25 s.

**Done when** both demo scenarios have audio by H+3, plus a script that regenerates it.

## Ameya's own tasks (not agents)
Twilio account, number and webhook; named `cloudflared` tunnel; enrolling both phones; the H+1 SMS check (outbound and inbound on the real phone, median and worst delivery over 10 sends, real segment count). If it fails, the demo uses `SimulatedGateway` and the pitch says so.
