#!/usr/bin/env python3
"""Safe Signal verification harness. Run through `make verify*` or:

  env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --with playwright==1.64.1 \\
      python .agents/skills/verify-app/scripts/verify.py <command>

Commands:
  run [--features a,b] [--checks id,..] [--changed BASE] [--negative-control] [--allow-blocked] [--keep-sandbox]
      Launch isolated instance(s), run journeys, write .verify/runs/<id>/report.{json,md}, clean up.
      Exit 0 = every selected check PASS; 1 = any FAIL; 2 = no FAIL but something BLOCKED.
  launch [--profile cached|asr] [--no-ui]   Start an instance for manual driving (prints URLs + password).
  doctor                                    Read-only health of the launched instance.
  cleanup                                   Stop the launched instance and delete its sandbox (keeps evidence).
  status                                    Show lock/instance state and the latest report.
  list                                      List checks by feature.
  affected [--base REF] [--json]            Map changed files to features (what `--changed` would run).
  lint                                      Detect drift between docs, coverage map, harness, routes and UI.
  sync [--report PATH] [--features a,b]     Advance synced_commit for features verified at HEAD.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402

import checks as C  # noqa: E402
import harness as H  # noqa: E402
import maint as M  # noqa: E402
from context import Context, Fail  # noqa: E402

PROFILE_ORDER = ["cached", "asr", "cli"]
EXIT = {"PASS": 0, "FAIL": 1, "BLOCKED": 2}


def select(args) -> tuple[list[C.Check], dict]:
    sel: dict = {}
    pool = [c for c in C.CHECKS if not c.control]
    if args.checks:
        ids = set(args.checks.split(","))
        unknown = ids - {c.id for c in C.CHECKS}
        if unknown:
            sys.exit(f"unknown check ids: {', '.join(sorted(unknown))} (see `verify.py list`)")
        pool = [c for c in C.CHECKS if c.id in ids]
    if args.features:
        feats = set(args.features.split(","))
        pool = [c for c in pool if c.feature in feats]
        sel["features"] = sorted(feats)
    if args.changed:
        aff = M.affected(args.changed)
        sel["changed"] = aff
        pool = [c for c in pool if c.feature in aff["features"]]
    if args.negative_control:
        pool += [c for c in C.CHECKS if c.control and c not in pool]
    ids = {c.id for c in pool}
    added = True
    while added:  # dependency closure
        added = False
        for c in list(pool):
            for r in c.requires:
                if r not in ids:
                    ids.add(r)
                    added = True
    chosen = [c for c in C.CHECKS if c.id in ids]
    sel["checks"] = [c.id for c in chosen]
    return chosen, sel


def environment(digest: str | None) -> dict:
    def ver(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip().splitlines()[0]
        except Exception:
            return None
    try:
        import importlib.metadata as md
        pw = md.version("playwright")
    except Exception:
        pw = None
    return {"git_head": H.git("rev-parse", "HEAD"), "git_branch": H.git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(H.git("status", "--porcelain")), "snapshot_digest": digest, "repo": str(H.REPO),
            "python": sys.version.split()[0], "node": ver(["node", "--version"]), "playwright": pw,
            "platform": platform.platform(), "host": platform.node(), "hf_home_default": str(H.DEFAULT_HF_HOME)}


class Runner:
    def __init__(self, run_id: str, evidence: Path):
        self.run_id, self.ev = run_id, evidence
        self.records: list[dict] = []
        self.instances: list[dict] = []
        self.logf = open(evidence / "commands.log", "a")

    def log(self, msg: str) -> None:
        line = f"{H.now()} {msg}"
        print(msg, flush=True)
        self.logf.write(line + "\n")
        self.logf.flush()

    def record(self, c: C.Check, status: str, reason: str = "", category: str = "", **extra) -> dict:
        rec = {"id": c.id, "feature": c.feature, "profile": c.profile, "ui": c.ui, "control": c.control,
               "status": status, "reason": reason, "category": category, "started_at": H.now(), "ended_at": H.now(),
               "duration_s": 0.0, "assertions": [], "actions": [], "evidence": [], **extra}
        self.records.append(rec)
        return rec

    def run_check(self, ctx: Context, c: C.Check) -> dict:
        unmet = [r for r in c.requires if r not in ctx.passed]
        if unmet:
            rec = self.record(c, "BLOCKED", f"requires {', '.join(unmet)} to PASS earlier in this run", "precondition")
            self.log(f"  BLOCKED {c.id}: {rec['reason']}")
            return rec
        rec = self.record(c, "RUNNING")
        ctx.rec = rec
        t0 = time.monotonic()
        self.log(f"  ▶ {c.id}")
        try:
            c.fn(ctx)
            if not rec["assertions"]:
                rec.update(status="BLOCKED", reason="check executed no assertions", category="harness-error")
            else:
                rec["status"] = "PASS"
                ctx.passed.add(c.id)
        except Fail as e:
            rec.update(status="FAIL", reason=str(e), category=e.category)
        except H.Blocked as e:
            rec.update(status="BLOCKED", reason=str(e), category="precondition")
        except httpx.HTTPError as e:
            rec.update(status="FAIL", reason=f"app request failed: {type(e).__name__}: {e}", category="app-unreachable")
        except Exception as e:
            name = type(e).__name__
            if type(e).__module__.startswith("playwright"):
                first = str(e).strip().splitlines()[0] if str(e).strip() else name
                rec.update(status="FAIL", category="ui-locator",
                           reason=f"{name}: {first} -- UI handle missing or not actionable: UI regression OR "
                                  "verification drift; run `verify.py lint` and compare with the screenshot")
            else:
                rec.update(status="BLOCKED", category="harness-error", reason=f"{name}: {e}",
                           traceback=traceback.format_exc()[-3000:])
        if c.known_gap and rec["status"] == "FAIL" and rec["category"] == "app-behavior":
            rec.update(status="KNOWN-GAP", known_gap=c.known_gap)
        elif c.known_gap and rec["status"] == "PASS":
            rec["known_gap_passed"] = c.known_gap
            self.log(f"  ! {c.id} is marked known gap {c.known_gap} but PASSED: remove known_gap= in checks.py")
        rec["ended_at"] = H.now()
        rec["duration_s"] = round(time.monotonic() - t0, 2)
        if rec["status"] != "PASS":
            try:
                ctx.shot("on-" + rec["status"].lower())
            except Exception:
                pass
        mark = {"PASS": "✓", "FAIL": "✗", "BLOCKED": "∅", "KNOWN-GAP": "~"}[rec["status"]]
        self.log(f"  {mark} {rec['status']} {c.id} ({rec['duration_s']}s){' - ' + rec['reason'] if rec['reason'] else ''}")
        return rec

    def run_profile(self, profile: str, chosen: list[C.Check], sandbox: Path) -> None:
        self.log(f"== profile {profile}: {len(chosen)} check(s)")
        if profile == "cli":
            inst = {"run_id": self.run_id, "profile": "cli", "sandbox": str(sandbox), "env": H.sandbox_env(sandbox, "cli", None),
                    "backend": None, "console": None, "procs": []}
            ctx = Context(inst, self.ev, self.log)
            for c in chosen:
                self.run_check(ctx, c)
            return
        inst = ctx = None
        relaunched = False
        pending = list(chosen)
        ui = any(c.ui for c in chosen)
        while pending:
            if inst is None:
                try:
                    inst = H.launch(self.run_id, sandbox, self.ev, profile, ui, self.log)
                    doc = H.doctor(inst)
                    self.instances.append({k: inst[k] for k in ("profile", "backend", "console")} | {"doctor": doc})
                    self.log(f"  doctor: {'healthy' if H.healthy(doc) else 'UNHEALTHY'} "
                             + ", ".join(f"{d['name']}={'ok' if d['ok'] else 'NO'}" for d in doc))
                    if not H.healthy(doc):
                        raise H.Blocked("doctor failed: " + "; ".join(d["detail"] for d in doc if not d["ok"]))
                    ctx = Context(inst, self.ev, self.log)
                    if any(r["status"] == "PASS" for r in self.records):
                        ctx.passed = {r["id"] for r in self.records if r["status"] == "PASS"}
                except H.Blocked as e:
                    self.log(f"  launch BLOCKED: {e}")
                    for c in pending:
                        self.record(c, "BLOCKED", f"instance ({profile}) unavailable: {e}", "launch")
                    if inst:
                        H.stop(inst, self.log)
                    return
            c = pending.pop(0)
            rec = self.run_check(ctx, c)
            if rec["status"] == "FAIL":
                doc = H.doctor(inst)
                rec["doctor_after"] = doc
                if not H.healthy(doc):
                    self.log("  instance unhealthy after failure -> relaunch" if not relaunched else "  unhealthy again")
                    ctx.close()
                    H.stop(inst, self.log)
                    inst = ctx = None
                    if relaunched:
                        for c2 in pending:
                            self.record(c2, "BLOCKED", "instance unhealthy twice; not driving it", "launch")
                        return
                    relaunched = True
        if ctx:
            ctx.close()
        if inst:
            H.stop(inst, self.log)


def coverage_summary(records: list[dict], chosen_features: set[str]) -> dict:
    cov = M.load_coverage()
    feats = {}
    for name in cov["features"]:
        recs = [r for r in records if r["feature"] == name]
        if not recs:
            status = "not-run"
        elif any(r["status"] == "FAIL" for r in recs):
            status = "failed"
        elif all(r["status"] == "PASS" for r in recs) and len(recs) == len([c for c in C.CHECKS if c.feature == name]):
            status = "verified"
        elif all(r["status"] == "PASS" for r in recs):
            status = "partially-verified"
        elif all(r["status"] in ("PASS", "KNOWN-GAP") for r in recs):
            status = "known-gap"
        else:
            status = "blocked"
        feats[name] = {"status": status, "checks": {r["id"]: r["status"] for r in recs}}
    return {"features": feats, "external_unverified": cov["external"],
            "not_run": [n for n, f in feats.items() if f["status"] == "not-run"]}


def write_report(run_id: str, ev: Path, started: str, env: dict, sel: dict, runner: Runner, iso: dict, cleanup: dict) -> dict:
    recs = runner.records
    summary = {s: sum(r["status"] == s for r in recs) for s in ("PASS", "FAIL", "BLOCKED", "KNOWN-GAP")}
    verdict = "FAIL" if summary["FAIL"] else "BLOCKED" if summary["BLOCKED"] or not recs else "PASS"
    failed = [r["id"] for r in recs if r["status"] != "PASS"]
    script = ".agents/skills/verify-app/scripts/verify.py"
    rep = {
        "schema": "verify-app/report@1", "run_id": run_id, "started_at": started, "ended_at": H.now(),
        "verdict": verdict, "exit_code": EXIT[verdict], "summary": summary, "environment": env, "selection": sel,
        "instances": runner.instances, "isolation": iso, "cleanup": cleanup, "checks": recs,
        "coverage": coverage_summary(recs, set(sel.get("features", []))),
        "negative_controls": [{"id": r["id"], "status": r["status"], "behaved_correctly": r["status"] == "FAIL"}
                              for r in recs if r["control"]],
        "reproduce": {"all": "make verify",
                      "not_passed": f"make verify ARGS='--checks {','.join(failed)}'" if failed else None,
                      "direct": f"env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv run --with playwright==1.64.1 "
                                f"python {script} run" + (f" --checks {','.join(failed)}" if failed else "")},
    }
    (ev / "report.json").write_text(json.dumps(rep, indent=1))
    lines = [f"# Verification report {run_id}", "",
             f"Verdict: **{verdict}** (PASS {summary['PASS']} · FAIL {summary['FAIL']} · BLOCKED {summary['BLOCKED']}"
             f" · KNOWN-GAP {summary['KNOWN-GAP']})",
             f"Commit {env['git_head'][:10]} on {env['git_branch']}{' (dirty tree)' if env['dirty'] else ''} · "
             f"snapshot {env['snapshot_digest']} · {started} → {rep['ended_at']}", "",
             "| Check | Feature | Status | Time | Reason |", "|---|---|---|---|---|"]
    for r in recs:
        lines.append(f"| `{r['id']}` | {r['feature']} | {r['status']} | {r['duration_s']}s | {r['reason'].replace('|', '/')[:220]} |")
    gaps = [r for r in recs if r["status"] == "KNOWN-GAP" or r.get("known_gap_passed")]
    if gaps:
        lines += ["", "## Known product gaps", "", "Documented app bugs; a KNOWN-GAP does not fail the verdict.", ""]
        for r in gaps:
            lines.append(f"- `{r['id']}` {r['status']}: {r.get('known_gap') or r['known_gap_passed']}"
                         + (" -- PASSED unexpectedly: the gap looks fixed, remove its known_gap marker"
                            if r.get("known_gap_passed") else ""))
    lines += ["", "## Feature coverage", ""]
    for n, f in rep["coverage"]["features"].items():
        lines.append(f"- {n}: {f['status']}")
    lines += ["", "## Not verified by automation (external)", ""] + [f"- {x['item']}: {x['reason']}" for x in rep["coverage"]["external_unverified"]]
    lines += ["", f"Isolation: user data untouched = {iso.get('untouched')}", f"Cleanup: {cleanup}", "",
              "## Reproduce", "", f"- all: `{rep['reproduce']['all']}`"]
    if rep["reproduce"]["not_passed"]:
        lines.append(f"- not passed: `{rep['reproduce']['not_passed']}`")
    (ev / "report.md").write_text("\n".join(lines) + "\n")
    return rep


def cmd_run(args) -> int:
    chosen, sel = select(args)
    if args.changed:
        a = sel["changed"]
        print(f"changed vs {args.changed}: {len(a['changed'])} file(s) -> features {a['features'] or 'none'}"
              + (f" (full run: {a['full_run_because'][:3]})" if a["full_run_because"] else ""))
        if a["unmapped"]:
            print(f"  unmapped (triage with maintain-verification): {a['unmapped']}")
    if not chosen:
        print("nothing to verify for this selection (0 checks). Not a PASS: no check ran.")
        return 0 if args.changed else 2
    try:
        lock = H.RunLock().__enter__()
    except H.Blocked as e:
        print(f"BLOCKED: {e}")
        return 2
    try:
        run_id = H.new_run_id()
        ev = H.RUNS / run_id
        ev.mkdir(parents=True)
        started = H.now()
        runner = Runner(run_id, ev)
        runner.log(f"run {run_id}: {len(chosen)} check(s); evidence -> {ev}")
        fp0 = H.user_data_fingerprint()
        sandbox, digest = H.snapshot(run_id)
        runner.log(f"sandbox snapshot {digest} at {sandbox}")
        env = environment(digest)
        (ev / "environment.json").write_text(json.dumps(env, indent=1))
        cleanup = {}
        try:
            for profile in PROFILE_ORDER:
                group = [c for c in chosen if c.profile == profile]
                if group:
                    runner.run_profile(profile, group, sandbox)
        except KeyboardInterrupt:
            runner.log("interrupted")
            for r in runner.records:  # the check Ctrl-C landed in never finished
                if r["status"] == "RUNNING":
                    r.update(status="BLOCKED", reason="run interrupted during this check", category="interrupted",
                             ended_at=H.now())
            done = {r["id"] for r in runner.records}
            for c in chosen:
                if c.id not in done:
                    runner.record(c, "BLOCKED", "run interrupted before this check", "interrupted")
        finally:
            st = H.read_state()
            if st and st.get("run_id") == run_id:
                H.stop(st, runner.log)
            leftover = [p for i in [st] if i for p in i.get("procs", []) if H._ours(p["pid"], str(sandbox))]
            if args.keep_sandbox:
                cleanup = {"sandbox_removed": False, "sandbox": str(sandbox)}
            else:
                H.remove_sandbox(sandbox, runner.log)
                cleanup = {"sandbox_removed": not sandbox.exists()}
            cleanup["leftover_processes"] = leftover
        fp1 = H.user_data_fingerprint()
        iso = {"untouched": fp0 == fp1, "before": fp0, "after": fp1}
        rep = write_report(run_id, ev, started, env, sel, runner, iso, cleanup)
        if not iso["untouched"]:
            rep["verdict"], rep["exit_code"] = "FAIL", 1
            runner.log("ISOLATION BREACH: repo data/ or results/ changed during the run")
            (ev / "report.json").write_text(json.dumps(rep, indent=1))
        latest = H.RUNS / "latest"
        latest.unlink(missing_ok=True)
        latest.symlink_to(run_id)
        evidence_ok = (ev / "report.json").is_file() and all((ev / p).exists() for r in rep["checks"] for p in r["evidence"])
        runner.log(f"\nVERDICT {rep['verdict']}  PASS {rep['summary']['PASS']} · FAIL {rep['summary']['FAIL']} · "
                   f"BLOCKED {rep['summary']['BLOCKED']} · KNOWN-GAP {rep['summary']['KNOWN-GAP']}  "
                   f"evidence intact after cleanup: {evidence_ok}")
        runner.log(f"report: {ev / 'report.md'}")
        for nc in rep["negative_controls"]:
            runner.log(f"negative control {nc['id']}: {nc['status']} "
                       f"({'harness can fail - good' if nc['behaved_correctly'] else 'HARNESS CANNOT BE TRUSTED'})")
        code = rep["exit_code"]
        if code == 2 and args.allow_blocked:
            code = 0
        return code if evidence_ok else 1
    finally:
        lock.__exit__(None, None, None)


def cmd_launch(args) -> int:
    with H.RunLock():
        run_id = H.new_run_id()
        ev = H.RUNS / run_id
        ev.mkdir(parents=True)
        sandbox, digest = H.snapshot(run_id)
        try:
            inst = H.launch(run_id, sandbox, ev, args.profile, not args.no_ui, print)
        except H.Blocked as e:
            st = H.read_state()
            if st:
                H.stop(st)
            H.remove_sandbox(sandbox)
            print(f"BLOCKED: {e}")
            return 2
    print(json.dumps({"run_id": run_id, "backend": inst["backend"], "console": inst["console"],
                      "operator_password": inst["env"]["OPERATOR_PASSWORD"], "sandbox": inst["sandbox"],
                      "evidence": str(ev)}, indent=1))
    print("drive it, then: verify.py doctor | verify.py cleanup")
    return 0


def cmd_doctor(args) -> int:
    st = H.read_state()
    if not st:
        print("no launched instance (.verify/state.json absent)")
        return 2
    res = H.doctor(st)
    for r in res:
        print(f"{'ok ' if r['ok'] else 'NO '} {r['name']}: {r['detail']}")
    print("HEALTHY" if H.healthy(res) else "UNHEALTHY")
    return 0 if H.healthy(res) else 1


def cmd_cleanup(args) -> int:
    st = H.read_state()
    if st:
        H.stop(st)
        H.remove_sandbox(Path(st["sandbox"]))
    orphans = [p for p in H.SANDBOXES.glob("*") if p.is_dir()] if H.SANDBOXES.exists() else []
    for p in orphans:  # sandboxes with no live process of ours (crashed runs)
        if not (st and p.name == st["run_id"]):
            H.remove_sandbox(p)
    print(f"evidence kept in {H.RUNS}")
    return 0


def cmd_status(args) -> int:
    st = H.live_state()
    print(f"instance: {'running ' + st['run_id'] + ' ' + st['backend'] if st else 'none'}")
    rep = H.RUNS / "latest" / "report.json"
    if rep.exists():
        r = json.loads(rep.read_text())
        print(f"latest run {r['run_id']}: {r['verdict']} {r['summary']} at {r['environment']['git_head'][:10]}")
    return 0


def cmd_list(args) -> int:
    for c in C.CHECKS:
        print(f"{c.feature:18} {c.id:32} profile={c.profile:6} {'ui' if c.ui else 'api'}"
              f"{' requires=' + ','.join(c.requires) if c.requires else ''}{' (negative control)' if c.control else ''}"
              f"{' (known gap ' + c.known_gap + ')' if c.known_gap else ''}")
    return 0


def cmd_affected(args) -> int:
    a = M.affected(args.base)
    a["needs_ui"] = any(c.ui for c in C.CHECKS if c.feature in a["features"] and not c.control)
    if args.json:
        print(json.dumps(a, indent=1))
    else:
        print(f"{len(a['changed'])} changed file(s) vs {args.base}")
        print(f"features to verify: {', '.join(a['features']) or 'none'}")
        for k in ("full_run_because", "unmapped", "ignored"):
            if a[k]:
                print(f"{k}: {', '.join(a[k])}")
    return 0


def cmd_lint(args) -> int:
    res = M.lint(C.CHECKS, C.UI_HANDLES, C.API_ROUTES)
    for e in res["errors"]:
        print(f"ERROR {e}")
    for w in res["warnings"]:
        print(f"WARN  {w}")
    print(f"LINT {'FAIL' if res['errors'] else 'OK'} ({len(res['errors'])} errors, {len(res['warnings'])} warnings)")
    return 1 if res["errors"] else 0


def cmd_sync(args) -> int:
    return M.sync_from_report(Path(args.report) if args.report else None,
                              args.features.split(",") if args.features else None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="verify.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--features")
    r.add_argument("--checks")
    r.add_argument("--changed", metavar="BASE")
    r.add_argument("--negative-control", action="store_true")
    r.add_argument("--allow-blocked", action="store_true", help="exit 0 when nothing FAILED but something was BLOCKED")
    r.add_argument("--keep-sandbox", action="store_true")
    la = sub.add_parser("launch")
    la.add_argument("--profile", choices=["cached", "asr"], default="cached")
    la.add_argument("--no-ui", action="store_true")
    for name in ("doctor", "cleanup", "status", "list", "lint"):
        sub.add_parser(name)
    af = sub.add_parser("affected")
    af.add_argument("--base", default="origin/main")
    af.add_argument("--json", action="store_true")
    sy = sub.add_parser("sync")
    sy.add_argument("--report")
    sy.add_argument("--features")
    args = ap.parse_args(argv)
    os.umask(0o022)
    return {"run": cmd_run, "launch": cmd_launch, "doctor": cmd_doctor, "cleanup": cmd_cleanup, "status": cmd_status,
            "list": cmd_list, "affected": cmd_affected, "lint": cmd_lint, "sync": cmd_sync}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
