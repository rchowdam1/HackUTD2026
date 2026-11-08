"""Score scenario batches through Track A's decide (PRD §19.6).

    python -m eval.run --arms K,B --batch dev|H1 [--policy v1.0]

Writes results/latest.json (app.models.Results) and results/latest.md.
Scripted transcripts only (source "script"): no audio, no ASR, no pipeline.

Sealing H1: scenarios/H1.sha256 holds sha256 over the contents of
scenarios/H1/*.json concatenated in sorted filename order. Produce it with
    python -c "from eval.run import h1_digest; print(h1_digest())" > scenarios/H1.sha256
"""
from __future__ import annotations

import argparse
import hashlib
import math
import subprocess
import sys
from pathlib import Path

from app import intent
from app.models import ArmCounts, Discordant, Results, Scenario, Segment

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios"
RESULTS = ROOT / "results"
Z = 1.96
ARMS = ("K", "B", "C")


def h1_digest(scenarios_dir: Path = SCENARIOS) -> str:
    h = hashlib.sha256()
    for p in sorted((scenarios_dir / "H1").glob("*.json"), key=lambda p: p.name):
        h.update(p.read_bytes())
    return h.hexdigest()


def load_batch(batch: str, scenarios_dir: Path = SCENARIOS) -> list[Scenario]:
    if batch == "H1":
        seal = scenarios_dir / "H1.sha256"
        expected = seal.read_text().split()[0] if seal.exists() else None
        if expected != h1_digest(scenarios_dir):
            raise SystemExit("refusing to score H1: scenarios/H1.sha256 missing or does not match")
    paths = sorted((scenarios_dir / batch).glob("*.json"))
    if not paths:
        raise SystemExit(f"no scenarios in scenarios/{batch}/")
    scenarios = [Scenario.model_validate_json(p.read_text()) for p in paths]
    assert all(s.set == batch for s in scenarios), f"scenario with wrong set in {batch}"
    ids = [s.id for s in scenarios]
    if dupes := sorted({i for i in ids if ids.count(i) > 1}):
        raise SystemExit(f"duplicate scenario id in scenarios/{batch}/: {', '.join(dupes)}")
    return scenarios


def revision() -> str:
    """Short git sha of the measured tree, "-dirty" if it has uncommitted changes; "unknown" without git."""
    try:
        git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return git("rev-parse", "--short", "HEAD").strip() + ("-dirty" if git("status", "--porcelain").strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def predict(scenario: Scenario, arm: str, policy_version: str, decide) -> bool:
    intent.clear_cache()  # one scenario = one live session: no intent answers carried across
    segments = [Segment(seq=i, speaker=t.speaker, text=t.text, source="script")
                for i, t in enumerate(scenario.turns, 1)]
    return any(d.level == "action_warning" for d in decide(segments, arm, policy_version))


def counts(scenarios: list[Scenario], fired: dict[str, bool]) -> ArmCounts:
    scam = [s for s in scenarios if s.label == "scam"]
    benign = [s for s in scenarios if s.label == "benign"]
    hard = [s for s in benign if s.hard_benign]
    tp = sum(fired[s.id] for s in scam)
    fp = sum(fired[s.id] for s in benign)
    return ArmCounts(TP=tp, FN=len(scam) - tp, FP=fp, TN=len(benign) - fp,
                     hard_benign_fp=sum(fired[s.id] for s in hard), hard_benign_n=len(hard))


def wilson(k: int, n: int, z: float = Z) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def pct_down(x: float) -> str:
    return f"{math.floor(x * 1000 + 1e-9) / 10:.1f}%"


def pct_up(x: float) -> str:
    return f"{math.ceil(x * 1000 - 1e-9) / 10:.1f}%"


def discordant(scenarios, fired_k, fired_b) -> tuple[list[str], list[str]]:
    """Calls only K classified correctly, and calls only B classified correctly."""
    correct = lambda fired, s: fired[s.id] == (s.label == "scam")
    k_only = [s.id for s in scenarios if correct(fired_k, s) and not correct(fired_b, s)]
    b_only = [s.id for s in scenarios if correct(fired_b, s) and not correct(fired_k, s)]
    return k_only, b_only


def verdict(k_only: int, b_only: int) -> str:
    for winner, w, l in (("B", b_only, k_only), ("K", k_only, b_only)):
        if w >= 5 and l == 0:
            return f"{winner} wins: {w} one-directional discordant calls, 0 the other way."
    return (f"No win called: needs 5 or more discordant calls all in one direction "
            f"(have K-only {k_only}, B-only {b_only}).")


def report(batch: str, policy_version: str, scenarios, results: Results, fired, disc_ids,
           c_failures: int | None = None) -> str:
    n_scam = sum(s.label == "scam" for s in scenarios)
    n_benign = len(scenarios) - n_scam
    lines = [
        f"# Eval: batch {batch}, policy {policy_version}",
        "",
        f"Measured: revision {revision()}, arms {','.join(results.arms)}, policy {policy_version}.",
        "",
        f"**Scripted transcripts, not ASR.** {len(scenarios)} calls: {n_scam} scam, {n_benign} benign "
        f"({results.arms[next(iter(results.arms))].hard_benign_n} hard-benign).",
        "",
        "| Arm | TP | FN | FP | TN | Recall (Wilson 95% CI) | Hard-benign false alerts |",
        "|---|---|---|---|---|---|---|",
    ]
    for arm, c in results.arms.items():
        n = c.TP + c.FN
        lo, hi = wilson(c.TP, n)
        rec = f"{c.TP} of {n} = {pct_down(c.TP / n) if n else 'n/a'} ({pct_down(lo)} to {pct_up(hi)})"
        hb = f"{c.hard_benign_fp} of {c.hard_benign_n} (upper bound {pct_up(wilson(c.hard_benign_fp, c.hard_benign_n)[1])})"
        lines.append(f"| {arm} | {c.TP} | {c.FN} | {c.FP} | {c.TN} | {rec} | {hb} |")
    if results.discordant:
        k_ids, b_ids = disc_ids
        lines += ["", "## Paired B vs K",
                  f"Correct only under K: {results.discordant.K_only} ({', '.join(k_ids) or 'none'}).",
                  f"Correct only under B: {results.discordant.B_only} ({', '.join(b_ids) or 'none'}).",
                  verdict(results.discordant.K_only, results.discordant.B_only)]
    lines += ["", "## Errors per arm"]
    for arm in results.arms:
        fn = [s.id for s in scenarios if s.label == "scam" and not fired[arm][s.id]]
        fp = [s.id for s in scenarios if s.label == "benign" and fired[arm][s.id]]
        lines.append(f"- {arm}: missed scams: {', '.join(fn) or 'none'}; false alerts: {', '.join(fp) or 'none'}")
    if c_failures is not None:
        lines += ["", f"C: {c_failures} TypeSafe calls failed and fell back to arm B."]
    lines += ["", "Percentages: estimates and lower bounds rounded down, upper bounds rounded up. "
              "Sample is small; this is not a production accuracy claim."]
    return "\n".join(lines) + "\n"


def run(arms: list[str], batch: str, policy_version: str, decide,
        scenarios_dir: Path = SCENARIOS, out_dir: Path = RESULTS) -> Results:
    if not arms or len(set(arms)) != len(arms) or not set(arms) <= set(ARMS):
        raise SystemExit(f"bad arms {','.join(arms)}: give each of K, B, C at most once")
    if "C" in arms and not intent.enabled():
        raise SystemExit("refusing to score arm C: the intent model is off (set INTENT_MODEL=on and "
                         "TYPESAFE_API_KEY); without it C would just repeat B")
    scenarios = load_batch(batch, scenarios_dir)
    fired, c_failures = {}, None
    for arm in arms:
        before = intent.failures
        fired[arm] = {s.id: predict(s, arm, policy_version, decide) for s in scenarios}
        if arm == "C":
            c_failures = intent.failures - before
    disc_ids = discordant(scenarios, fired["K"], fired["B"]) if {"K", "B"} <= set(arms) else ([], [])
    results = Results(
        batch=batch,
        arms={arm: counts(scenarios, fired[arm]) for arm in arms},
        discordant=Discordant(K_only=len(disc_ids[0]), B_only=len(disc_ids[1])) if {"K", "B"} <= set(arms) else None,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "latest.json").write_text(results.model_dump_json(indent=2) + "\n")
    (out_dir / "latest.md").write_text(report(batch, policy_version, scenarios, results, fired, disc_ids,
                                              c_failures))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.run")
    ap.add_argument("--arms", default="K,B")
    ap.add_argument("--batch", required=True, choices=["dev", "H1"])
    ap.add_argument("--policy", default="v1.0")
    args = ap.parse_args(argv)
    from app.rules import decide
    run(args.arms.split(","), args.batch, args.policy, decide)
    print((RESULTS / "latest.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
