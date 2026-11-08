#!/usr/bin/env python3
"""Plan a maintenance pass for the verify-app and verify-pipeline-formal skills. Read-only.

  python3 .agents/skills/maintain-verification/scripts/plan.py [--base REF] [--all]

Writes .verify/maintenance/<timestamp>/plan.json and plan.md and prints the summary:
  - lint errors/warnings (drift between docs, coverage map, harness, UI strings, routes)
  - features to re-check: covered files changed since BASE (default: each feature's own
    synced_commit; never-synced features are always included), or every feature with --all
  - unmapped changed files (possible new user-facing surface)
  - formal check staleness: covered files changed since the sync commit in its SKILL.md
  - one read-only source-review brief per feature, ready to hand to a parallel subagent
Exit 0 always unless the planner itself breaks; the plan says what needs doing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERIFY_SCRIPTS = HERE.parents[1] / "verify-app" / "scripts"
sys.path.insert(0, str(VERIFY_SCRIPTS))

import harness as H  # noqa: E402
import maint as M  # noqa: E402

FORMAL_SKILL = HERE.parents[1] / "verify-pipeline-formal" / "SKILL.md"
FORMAL_FILES = ["backend/app/pipeline.py", "backend/app/ingest/__init__.py", "backend/app/api/demo.py"]

BRIEF = """You are a read-only source reviewer for the Safe Signal repo at {repo}. Do not edit files, run the app, or run git commands that change state.
Feature: {name}. Its verification recipe is {doc}; read it first.
Source paths this feature covers: {paths}.
{changed}Explain from source how this user-facing feature works now, then compare with the recipe.
Return exactly:
1. Feature summary (3-6 sentences, user point of view).
2. Source entry points (file:line for routes, UI handlers, CLI mains).
3. Likely drift: each recipe statement that no longer matches the code, with file:line evidence, or "none".
4. New behavior the recipe does not cover, with file:line, or "none".
5. One live-verification recipe (actions + observable results) that would prove the feature works now."""


def checks_by_feature() -> dict[str, list[str]]:
    import checks as C
    out: dict[str, list[str]] = {}
    for c in C.CHECKS:
        out.setdefault(c.feature, []).append(c.id)
    return out


def formal_status() -> dict:
    text = FORMAL_SKILL.read_text() if FORMAL_SKILL.exists() else ""
    m = re.search(r"Sync commit: `([0-9a-f]{7,40})`", text)
    if not m:
        return {"sync_commit": None, "changed": FORMAL_FILES, "note": "no sync commit recorded; treat as stale"}
    sync = m.group(1)
    changed = [f for f in H.git("diff", "--name-only", sync, "HEAD", "--", *FORMAL_FILES).splitlines() if f]
    changed += [f for f in H.git("diff", "--name-only", "HEAD", "--", *FORMAL_FILES).splitlines() if f and f not in changed]
    log = H.git("log", "--oneline", f"{sync}..HEAD", "--", *FORMAL_FILES).splitlines()
    return {"sync_commit": sync, "changed": changed, "commits": log}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="diff against this ref instead of per-feature sync commits")
    ap.add_argument("--all", action="store_true", help="plan every feature (periodic full pass)")
    a = ap.parse_args()
    import checks as C
    cov = M.load_coverage()
    lint = M.lint(C.CHECKS, C.UI_HANDLES, C.API_ROUTES)
    by_feature = checks_by_feature()
    feats = {}
    for name, spec in cov["features"].items():
        ref = a.base or spec.get("synced_commit")
        if a.all:
            reason, changed = "full pass requested", []
        elif not ref:
            reason, changed = "never synced", []
        else:
            files = M.changed_files(ref)
            changed = [f for f in files if M.matches(f, spec["paths"]) or M.matches(f, cov["global_paths"])]
            reason = f"{len(changed)} covered file(s) changed since {ref[:10]}" if changed else ""
        if reason:
            feats[name] = {"reason": reason, "changed": changed, "doc": f"features/{spec['doc']}",
                           "checks": by_feature.get(name, [])}
    aff = M.affected(a.base) if a.base else None
    unmapped = aff["unmapped"] if aff else [w.split()[3].rstrip(":") for w in lint["warnings"] if w.startswith("unmapped")]
    skill_rel = str(H.SKILL_DIR.relative_to(H.REPO))
    briefs = {n: BRIEF.format(repo=H.REPO, name=n, doc=f"{skill_rel}/{f['doc']}",
                              paths=", ".join(cov["features"][n]["paths"]),
                              changed=(f"Files changed since the last verified commit: {', '.join(f['changed'])}.\n"
                                       if f["changed"] else ""))
              for n, f in feats.items()}
    plan = {"created_at": H.now(), "head": H.git("rev-parse", "HEAD"), "base": a.base, "lint": lint,
            "features": feats, "unmapped": unmapped, "formal": formal_status(), "briefs": briefs,
            "live_command": ("make verify ARGS=\"--features " + ",".join(feats) + " --negative-control\"") if feats else None}
    out = H.HOME / "maintenance" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan, indent=1))
    md = [f"# Maintenance plan {out.name} at {plan['head'][:10]}", "",
          f"Lint: {len(lint['errors'])} errors, {len(lint['warnings'])} warnings"]
    md += [f"- ERROR {e}" for e in lint["errors"]] + [f"- WARN {w}" for w in lint["warnings"]]
    md += ["", "## Features to re-check (source wave + live pass)", ""]
    md += [f"- {n}: {f['reason']} (checks: {', '.join(f['checks'])})" for n, f in feats.items()] or ["- none"]
    md += ["", "## Unmapped files", ""] + ([f"- {u}" for u in unmapped] or ["- none"])
    fs = plan["formal"]
    md += ["", "## Formal check", "", f"sync commit {fs['sync_commit']}; covered files changed: {', '.join(fs['changed']) or 'none'}"]
    md += ["", "## Live command", "", f"`{plan['live_command']}`" if plan["live_command"] else "none needed"]
    md += ["", "## Source-wave briefs", ""] + [f"### {n}\n\n```\n{b}\n```\n" for n, b in briefs.items()]
    (out / "plan.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[: md.index("## Source-wave briefs")]))
    print(f"plan: {out / 'plan.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
