# Results card

The console's footer shows the held-out evaluation: per-arm scam calls caught and hard-benign false alerts, discordant counts, and a "Where we fail" card with arm B's misses. Before any results exist it says "Results pending". Track C produces the numbers with `python -m eval.run`, which writes `results/latest.json`; `GET /results/latest` serves that file unchanged.

## Sub-features

- `results.pending` serves `{"status":"pending"}` with no results file and shows "Results pending" without measured misses.
- `results.eval-cli-to-card` runs `python -m eval.run --arms K,B --batch dev`, then proves the API serves the file byte-for-byte and both cards show its numbers.

## How to get to it (user POV)

- Console footer cards `Held-out results` and `Where we fail` (refresh every 30 s or on reload).
- `python -m eval.run --arms K,B --batch dev|H1` from the repo root; `GET /results/latest` (cookie required).

## Driving it with verify.py

Preconditions:

- Profile `cached` with the console. The sandbox has the committed `results/latest.json` (H1 numbers).

- **Pending.** The check renames the sandbox's `results/latest.json` to `latest.json.verify-aside`. `GET /results/latest` returns exactly `{"status": "pending"}`; the `Held-out results` card contains `Results pending`; `Where we fail` contains no `Missed`.
- **Eval CLI.** In the sandbox run `python -m eval.run --arms K,B --batch dev` (sandbox env, `PYTHONPATH` = sandbox). Exit 0; `results/latest.json` has `batch: dev` and arms K and B; `GET /results/latest` bytes equal the file bytes.
- **Card.** Reload the console. The card heading reads `Held-out results · dev`; the `Keyword only (K)` and `CallSafe rules (B)` blocks contain `Scam calls caught: TP of TP+FN` and `hard_benign_fp of hard_benign_n` from the file; `Where we fail` contains `Missed FN of TP+FN scam calls` for arm B.
- **Proof.** `artifacts/results.eval-cli-to-card--eval-stdout.txt` (command, exit code, output), `artifacts/results.eval-cli-to-card--latest.json`, `screenshots/results.*`.

## Gotchas

- The card polls every 30 s; reload instead of waiting.
- H1 scoring is out of scope for Track A agents (never read `scenarios/H1/`); the snapshot excludes it, so `--batch H1` would fail in the sandbox by design. Use `--batch dev`.
- `eval.run` writes relative to its own file (`ROOT/results`); run it from the sandbox with the sandbox on `PYTHONPATH`, or it overwrites the checkout's committed results.
- "Where we fail" always shows three static bullets; only the `Missed …` and `False alerts …` lines come from the file.
