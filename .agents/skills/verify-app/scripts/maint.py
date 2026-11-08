"""Maintenance helpers: map changed files to features, lint the verification system for
drift, and advance per-feature sync commits only from a passing report."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from harness import REPO, RUNS, SKILL_DIR, git

COVERAGE = SKILL_DIR / "features" / "coverage.json"
FEATURES_DIR = SKILL_DIR / "features"
SOURCE_ROOTS = ("backend/app/", "console/src/", "console/index.html", "scripts/", "eval/", "policy/",
                "scenarios/demo/", "audio/demo/")


def load_coverage() -> dict:
    return json.loads(COVERAGE.read_text())


def _rx(glob: str) -> re.Pattern:
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**", i):
            out, i = out + ".*", i + 2
        elif glob[i] == "*":
            out, i = out + "[^/]*", i + 1
        else:
            out, i = out + re.escape(glob[i]), i + 1
    return re.compile(out + "$")


def matches(path: str, globs: list[str]) -> bool:
    return any(_rx(g).match(path) for g in globs)


def tracked_files() -> list[str]:
    return [f for f in git("ls-files", "-co", "--exclude-standard").splitlines() if f]


def changed_files(base: str) -> list[str]:
    files = set()
    merge_base = git("merge-base", base, "HEAD") or base
    for args in (("diff", "--name-only", f"{merge_base}", "HEAD"), ("diff", "--name-only", "HEAD"),
                 ("ls-files", "--others", "--exclude-standard")):
        files |= {f for f in git(*args).splitlines() if f}
    return sorted(files)


def affected(base: str, files: list[str] | None = None) -> dict:
    cov = load_coverage()
    files = changed_files(base) if files is None else files
    feats: set[str] = set()
    full, unmapped, ignored = [], [], []
    skill_prefix = str(SKILL_DIR.relative_to(REPO)) + "/"
    for f in files:
        hit = {n for n, spec in cov["features"].items() if matches(f, spec["paths"])}
        if f.startswith(skill_prefix + "features/") and f.endswith(".md") and not f.endswith("README.md"):
            hit |= {n for n, spec in cov["features"].items() if f.endswith("/" + spec["doc"])}
        if hit:
            feats |= hit
        elif matches(f, cov["global_paths"]) or f.startswith(skill_prefix):
            full.append(f)
        elif matches(f, cov["ignored_paths"]):
            ignored.append(f)
        else:
            unmapped.append(f)
    if full:
        feats = set(cov["features"])
    return {"base": base, "changed": files, "features": sorted(feats), "full_run_because": full,
            "unmapped": unmapped, "ignored": ignored}


# --- lint ------------------------------------------------------------------------------------

def declared_routes() -> set[str]:
    routes = set()
    for py in (REPO / "backend/app").rglob("*.py"):
        src = py.read_text()
        m = re.search(r'APIRouter\(\s*prefix\s*=\s*"([^"]+)"', src)
        prefix = m.group(1) if m else ""
        for d in re.finditer(r'@router\.(?:get|post|put|delete|patch)\(\s*"([^"]*)"', src):
            routes.add(prefix + d.group(1))
    return routes


def lint(checks, ui_handles, api_routes) -> dict:
    cov = load_coverage()
    errors, warnings = [], []
    feats = cov["features"]
    docs = {p.name for p in FEATURES_DIR.glob("*.md") if p.name != "README.md"}
    readme = (FEATURES_DIR / "README.md").read_text()
    for name, spec in feats.items():
        if spec["doc"] not in docs:
            errors.append(f"coverage.json feature {name}: doc features/{spec['doc']} missing")
        if f"({'./' + spec['doc']})" not in readme:
            errors.append(f"features/README.md does not link ./{spec['doc']}")
    for d in docs - {s["doc"] for s in feats.values()}:
        errors.append(f"features/{d} is not registered in coverage.json")
    for link in re.findall(r"\]\(\./([^)]+\.md)\)", readme):
        if link not in docs:
            errors.append(f"features/README.md links missing ./{link}")
    ids = {c.id for c in checks}
    for c in checks:
        if not c.control and c.feature not in feats:
            errors.append(f"check {c.id}: feature {c.feature} not in coverage.json")
        for r in c.requires:
            if r not in ids:
                errors.append(f"check {c.id} requires unknown check {r}")
    for name, spec in feats.items():
        mine = {c.id for c in checks if c.feature == name}
        if not mine:
            errors.append(f"feature {name} has no executable check")
        doc = FEATURES_DIR / spec["doc"]
        if doc.exists():
            text = doc.read_text()
            for cid in mine - set(re.findall(r"`([a-z]+\.[a-z0-9-]+)`", text)):
                errors.append(f"features/{spec['doc']} does not document check `{cid}`")
            for cid in set(re.findall(r"`([a-z]+\.[a-z0-9-]+)`", text)) - ids:
                if re.match(r"^(login|fixtures|results|replay|replies|controls|webhooks|invite|asr|preflight|control)\.", cid):
                    errors.append(f"features/{spec['doc']} names check `{cid}` that no longer exists")
            h2 = re.findall(r"^## (.+)$", text, re.M)
            want = ["Sub-features", "How to get to it (user POV)", "Driving it with verify.py", "Gotchas"]
            if h2 != want:
                errors.append(f"features/{spec['doc']}: H2s {h2} != {want}")
    tracked = tracked_files()
    for name, spec in feats.items():
        for g in spec["paths"]:
            if not any(_rx(g).match(f) for f in tracked):
                errors.append(f"feature {name}: path {g} matches no file (renamed or deleted?)")
    console_src = "\n".join(p.read_text() for p in sorted((REPO / "console/src").glob("*.ts*")))  # UI text can live in api.ts
    for h in ui_handles:
        # whole-phrase match: "Run bank" must not be satisfied by "Run bank call" (locators use exact names)
        if not re.search(r"(?<![A-Za-z] )(?<!\w)" + re.escape(h) + r"(?!\w)(?! [A-Za-z])", console_src):
            errors.append(f"UI handle {h!r} not found in console/src (renamed? update checks.py + feature doc)")
    routes = declared_routes()
    for r in api_routes:
        if r not in routes:
            errors.append(f"route {r} no longer declared in backend/app")
    all_globs = [g for s in feats.values() for g in s["paths"]] + cov["global_paths"] + cov["ignored_paths"]
    for f in tracked:
        if f.startswith(SOURCE_ROOTS) and not matches(f, all_globs):
            warnings.append(f"unmapped source file {f}: new user-facing surface? map it or ignore it in coverage.json")
    skill_md = (SKILL_DIR / "SKILL.md").read_text()
    for script in set(re.findall(r"scripts/([a-z_]+\.py)", skill_md)):
        if not (SKILL_DIR / "scripts" / script).exists() and not (REPO / "scripts" / script).exists():
            errors.append(f"SKILL.md references scripts/{script}, found neither in the skill nor the repo")
    for name, spec in feats.items():
        sync = spec.get("synced_commit")
        if not sync:
            warnings.append(f"feature {name}: never synced (no passing run recorded)")
            continue
        if subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", sync + "^{commit}"], capture_output=True).returncode:
            warnings.append(f"feature {name}: synced_commit {sync[:10]} not in this clone")
            continue
        changed = [f for f in git("diff", "--name-only", sync, "HEAD").splitlines() if matches(f, spec["paths"])]
        if changed:
            warnings.append(f"feature {name}: {len(changed)} covered file(s) changed since sync {sync[:10]} "
                            f"({', '.join(changed[:4])}) -> re-verify")
    return {"errors": errors, "warnings": warnings}


# --- sync ------------------------------------------------------------------------------------

def sync_from_report(report_path: Path | None, only: list[str] | None, log=print) -> int:
    report_path = report_path or (RUNS / "latest" / "report.json")
    rep = json.loads(Path(report_path).read_text())
    env = rep["environment"]
    if env.get("dirty"):
        log(f"refusing: report {rep['run_id']} ran on a dirty tree; commit first and re-run so the sync commit "
            "describes what was verified")
        return 1
    if env["git_head"] != git("rev-parse", "HEAD"):
        log(f"refusing: report ran at {env['git_head'][:10]}, HEAD is {git('rev-parse', 'HEAD')[:10]}")
        return 1
    cov = load_coverage()
    moved = []
    for name, f in rep["coverage"]["features"].items():
        if name not in cov["features"] or (only and name not in only):
            continue
        if f["status"] == "verified":
            cov["features"][name]["synced_commit"] = env["git_head"]
            moved.append(name)
        else:
            log(f"not syncing {name}: {f['status']}")
    COVERAGE.write_text(json.dumps(cov, indent=2) + "\n")
    log(f"synced {', '.join(moved) or 'nothing'} to {env['git_head'][:10]}")
    return 0
