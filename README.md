# Safe Signal (HackUTD 2026)

Safe Signal texts you during a call when the caller asks for a code, money or access to your device. The text names the request and gives one safe step. The demo replays two calls through the live pipeline: a clinic call that must stay silent, and a bank call that turns into a request for a one-time passcode (OTP). An operator console shows the transcript, why an alert fired, and the held-out results. `PRD.md` §19 is the build spec.

## Stack

- Backend: Python 3.11, FastAPI and uvicorn in one process (`backend/app`).
- Speech to text: faster-whisper `small.en` on CPU, with a cached transcript as fallback.
- Rules and SMS templates: YAML files in `policy/v1.0`.
- Storage: SQLite in `data/`, which holds only hashed phone numbers.
- SMS: Photon Spectrum iMessage (Bun bridge in `hackutd/`), or a simulated phone.
- Operator console: React + TypeScript + Vite (`console/`).
- Evaluation scripts: `eval/`.
- Tooling: `uv` and pytest.

## Run

```bash
make install                      # uv sync
make run                          # backend on :8000 (needs OPERATOR_PASSWORD, SESSION_SECRET, CONSENT_SALT set)
cd console && npm ci && npm run dev   # operator console; proxies the API to :8000
make demo-up                      # demo laptop: tunnel + Photon bridge + app (docs/photon-live.md)
scripts/preflight                 # go/no-go before judging
python -m eval.run --arms K,B --batch dev   # writes results/latest.json and .md
```

`.env.example` lists the variable names. Never commit `.env`.

## Test and verify

```bash
make test            # pytest
make smoke           # pytest + OTP fixture replay (required before merging)
make verify-changed  # live verification of the features your branch touched
make verify          # live verification of everything (~4 min)
make verify-lint     # check that the verification docs and checks still match the code
make verify-formal   # TLA+ model check of the call-session pipeline
```

`make verify` launches the real app in an isolated sandbox. It never uses your `.env`, your data or a real phone. It drives the console and API the way a user would and writes evidence to `.verify/runs/<id>/report.md`. See [docs/verification.md](docs/verification.md).

## Working in this repo

Agents and humans follow [AGENTS.md](AGENTS.md): each works on their own branch and worktree, uses the message board (issue #1), and works from task issues.
