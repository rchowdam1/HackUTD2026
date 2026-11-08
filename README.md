# CallSafe (HackUTD 2026)

CallSafe texts you during a call when the caller asks for a code, money or access to your device. The text names the request and gives one safe step. The demo replays two calls through the live pipeline: a clinic call that must stay silent, and a bank call that turns into a request for a one-time passcode (OTP). An operator console shows the transcript, why an alert fired, and the held-out results. `PRD.md` §19 is the build spec.

The demo runs arm B (rules + policy) in simulated SMS mode: the console's phone frame shows the texts and has on-screen reply buttons. The Twilio account is still a trial (no number, can't send our message bodies), and real SMS needs an upgraded account plus 10DLC or toll-free registration, which takes days.

## Stack

- Backend: Python 3.11, FastAPI and uvicorn in one process (`backend/app`).
- Speech to text: faster-whisper `small.en` on CPU, with a cached transcript as fallback.
- Rules and SMS templates: YAML files in `policy/v1.0`.
- Storage: SQLite in `data/`. Phone numbers are stored only as HMACs keyed by `CONSENT_SALT`; no audio or transcripts.
- SMS: Twilio Programmable Messaging, or a simulated phone.
- Arm C adds the TypeSafe Jev API (an external call, so call text leaves the machine). It needs `INTENT_MODEL=on` and `TYPESAFE_API_KEY`; without them C equals B. A failed TypeSafe call falls back to arm B for that turn. The API currently returns HTTP 402 (out of credit), so C equals B until credit is added.
- Operator console: React + TypeScript + Vite (`console/`).
- Evaluation scripts: `eval/`.
- Tooling: `uv` and pytest.

## Run

```bash
make install                      # uv sync
make run                          # backend on :8000 (needs OPERATOR_PASSWORD, SESSION_SECRET, CONSENT_SALT set)
cd console && npm ci && npm run dev   # operator console; proxies the API to :8000
make demo-up                      # demo laptop: tunnel (Twilio webhooks only) + app on 127.0.0.1 (docs/twilio-live.md)
scripts/preflight                 # go/no-go before judging
python -m eval.run --arms K,B --batch dev   # writes results/latest.json and .md
```

`.env.example` lists the variable names. Never commit `.env`.

## Test and verify

```bash
make test            # pytest
make smoke           # ruff + pytest + OTP fixture replay (required before merging)
make verify-changed  # live verification of the features your branch touched
make verify          # live verification of everything (~4 min)
make verify-lint     # check that the verification docs and checks still match the code
make verify-formal   # TLA+ model check of the call-session pipeline
```

`make verify` launches the real app in an isolated sandbox. It never uses your `.env`, your data or a real phone. It drives the console and API the way a user would and writes evidence to `.verify/runs/<id>/report.md`. See [docs/verification.md](docs/verification.md).

## Working in this repo

Agents and humans follow [AGENTS.md](AGENTS.md): each works on their own branch and worktree, and works from task issues. There is no message board.
