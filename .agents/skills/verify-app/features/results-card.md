# Results card

Track C produces the held-out numbers with `python -m eval.run`, which writes `results/latest.json`; `GET /results/latest` serves that file unchanged, or `{"status": "pending"}` when there is none. The console no longer shows them (removed from the demo screen on 2026-11-08); the deck quotes them.

## Sub-features

- `results.pending` serves `{"status":"pending"}` with no results file.
- `results.eval-cli-to-api` runs `python -m eval.run --arms K,B --batch dev`, then proves the API serves the file byte-for-byte.

## How to get to it (user POV)

- `python -m eval.run --arms K,B --batch dev|H1` from the repo root; `GET /results/latest` (cookie required).

## Driving it with verify.py

Preconditions:

- Profile `cached`. The sandbox has the committed `results/latest.json` (H1 numbers).

- **Pending.** The check renames the sandbox's `results/latest.json` to `latest.json.verify-aside`. `GET /results/latest` returns exactly `{"status": "pending"}`.
- **Eval CLI.** In the sandbox run `python -m eval.run --arms K,B --batch dev` (sandbox env, `PYTHONPATH` = sandbox). Exit 0; `results/latest.json` has `batch: dev` and arms K and B; `GET /results/latest` bytes equal the file bytes.
- **Proof.** `artifacts/results.eval-cli-to-api--eval-stdout.txt` (command, exit code, output), `artifacts/results.eval-cli-to-api--latest.json`.

## Gotchas

- H1 scoring is out of scope for Track A agents (never read `scenarios/H1/`); the snapshot excludes it, so `--batch H1` would fail in the sandbox by design. Use `--batch dev`.
- `eval.run` writes relative to its own file (`ROOT/results`); run it from the sandbox with the sandbox on `PYTHONPATH`, or it overwrites the checkout's committed results.
