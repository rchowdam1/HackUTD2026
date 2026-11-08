"""Launch, doctor and clean up an isolated Safe Signal instance for verification.

Isolation model: the app hard-wires its SQLite DB and results file to paths under
the repo root (`data/`, `results/`), so verification never runs the app from the
checkout. It copies the working tree (tracked + untracked, not ignored, minus
scenarios/H1/) into `.verify/sandbox/<run_id>/` and runs uvicorn with that copy
first on sys.path. The sandbox gets throwaway secrets and fictional 555 numbers and
never sees `.env`, so no real SMS can be sent and no real data is touched.

Evidence lives in `.verify/runs/<run_id>/` and survives cleanup.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO = Path(subprocess.check_output(["git", "-C", str(SKILL_DIR), "rev-parse", "--show-toplevel"], text=True).strip())
HOME = Path(os.environ.get("VERIFY_HOME") or REPO / ".verify")
RUNS = HOME / "runs"
SANDBOXES = HOME / "sandbox"
STATE = HOME / "state.json"
LOCK = HOME / "lock"
DEFAULT_HF_HOME = Path.home() / ".cache" / "huggingface"
WHISPER_MODEL_DIR = "models--Systran--faster-whisper-small.en"
SNAPSHOT_EXCLUDE = ("scenarios/H1/", "scenarios/H1.sha256")  # Track A never reads H1 (PRD §19.10)
DEMO_PHONE = "+15550100001"   # fictional 555-01xx numbers: never routable, never texted
SPARE_PHONE = "+15550100002"


class Blocked(Exception):
    """Verification could not run (missing dependency, launch failure). Never a pass."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True).stdout.strip()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- concurrency guard -------------------------------------------------------------------------

class RunLock:
    """Exclusive lock for one live verification at a time (shared ports/browser are not the
    issue; serial runs keep evidence and timing deterministic). Non-blocking: a second run
    is BLOCKED, never queued silently."""

    def __init__(self) -> None:
        HOME.mkdir(parents=True, exist_ok=True)
        self.fh = open(LOCK, "a+")

    def __enter__(self):
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Blocked(f"another verification run holds {LOCK}; wait for it or run `verify.py status`") from None
        live = live_state()
        if live:
            fcntl.flock(self.fh, fcntl.LOCK_UN)
            raise Blocked(f"a launched instance is still running (run {live['run_id']}); "
                          f"`verify.py cleanup` it first")
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.fh, fcntl.LOCK_UN)
        self.fh.close()


# --- state file (for manual launch/doctor/cleanup) ---------------------------------------------

def read_state() -> dict | None:
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _ours(pid: int, marker: str) -> bool:
    """True only if pid is alive AND its command line mentions our sandbox (guards pid reuse)."""
    try:
        return marker in Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False


def live_state() -> dict | None:
    st = read_state()
    if st and any(_ours(p["pid"], st["sandbox"]) for p in st.get("procs", [])):
        return st
    return None


# --- sandbox -----------------------------------------------------------------------------------

def snapshot(run_id: str) -> tuple[Path, str]:
    """Copy the working tree into a sandbox. Returns (sandbox, content digest of copied files)."""
    sandbox = SANDBOXES / run_id
    sandbox.mkdir(parents=True)
    files = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "-co", "--exclude-standard"],
                           capture_output=True, check=True).stdout.split(b"\0")
    h = hashlib.sha256()
    for raw in sorted(f for f in files if f):
        rel = raw.decode()
        src = REPO / rel
        if rel.startswith(SNAPSHOT_EXCLUDE) or rel.startswith(".verify/") or not src.is_file():
            continue
        dst = sandbox / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        h.update(rel.encode() + b"\0" + src.read_bytes())
    return sandbox, h.hexdigest()[:16]


def sandbox_env(sandbox: Path, profile: str, port: int | None) -> dict:
    """Clean environment for app processes: nothing inherited from the user's shell but
    PATH/HOME/locale, so a stray PHOTON_* or PYTHONPATH can't leak in."""
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "USER", "TMPDIR") if k in os.environ}
    hf_home = os.environ.get("VERIFY_HF_HOME") or str(DEFAULT_HF_HOME)
    env.update({
        "PYTHONPATH": f"{sandbox / 'backend'}:{sandbox}",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HOME": hf_home,
        "HF_HUB_OFFLINE": "1",            # the app must work offline (PRD §19.7); never download in a check
        "REPLAY_SOURCE": "asr" if profile == "asr" else "cached",
        "OPERATOR_PASSWORD": "verify-" + secrets.token_hex(8),
        "SESSION_SECRET": secrets.token_hex(16),
        "CONSENT_SALT": "verify-salt-" + secrets.token_hex(4),
        "DEMO_PHONE": DEMO_PHONE,
        "SPARE_PHONE": SPARE_PHONE,
        # Shared token for posting bridge-style inbound texts. The bridge URL points at the discard
        # port, so real-mode sends fail closed instead of reaching a local Photon bridge.
        "PHOTON_BRIDGE_TOKEN": "verify-" + secrets.token_hex(16),
        "PHOTON_BRIDGE_URL": "http://127.0.0.1:9",
    })
    if port:
        env["PUBLIC_BASE_URL"] = f"http://127.0.0.1:{port}"
    return env


def ensure_console_deps(sandbox: Path, log) -> None:
    console = sandbox / "console"
    cmd = ["npm", "ci", "--prefer-offline", "--no-audit", "--no-fund"]
    log("$ (cd sandbox/console) " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=console, capture_output=True, text=True)
    if r.returncode != 0 or not (console / "node_modules" / "vite" / "bin" / "vite.js").is_file():
        raise Blocked(f"npm ci failed in sandbox console (exit {r.returncode}): {r.stderr[-400:]}")


# --- launch ------------------------------------------------------------------------------------

def _spawn(cmd: list[str], cwd: Path, env: dict, logfile: Path) -> subprocess.Popen:
    out = open(logfile, "ab")
    # own session => own process group; cleanup kills only this group
    return subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)


def _wait_http(url: str, proc: subprocess.Popen, logfile: Path, timeout: float, ok=lambda r: r.status_code == 200):
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise Blocked(f"process exited ({proc.returncode}) before {url} was ready; log tail:\n"
                          + logfile.read_text(errors="replace")[-1500:])
        try:
            r = httpx.get(url, timeout=2)
            if ok(r):
                return r
            last = f"HTTP {r.status_code}"
        except httpx.HTTPError as e:
            last = type(e).__name__
        time.sleep(0.3)
    raise Blocked(f"{url} not ready after {timeout:.0f}s (last: {last})")


def launch(run_id: str, sandbox: Path, evidence: Path, profile: str, ui: bool, log) -> dict:
    """Start backend (+ Vite console if ui). Returns an instance dict; raises Blocked."""
    port = free_port()
    env = sandbox_env(sandbox, profile, port)
    if profile == "asr" and not (Path(env["HF_HOME"]) / "hub" / WHISPER_MODEL_DIR).is_dir():
        raise Blocked(f"faster-whisper small.en is not cached under HF_HOME={env['HF_HOME']}; "
                      "download once online (see scripts/preflight_checks.py MODEL_DOWNLOAD)")
    (sandbox / "verify.env.json").write_text(json.dumps(env, indent=1))
    blog = evidence / f"backend-{profile}.log"
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(sandbox / "backend"),
           "--host", "127.0.0.1", "--port", str(port), "--log-level", "info"]
    log("$ " + " ".join(cmd) + f"  (cwd sandbox, REPLAY_SOURCE={env['REPLAY_SOURCE']})")
    backend = _spawn(cmd, sandbox, env, blog)
    inst = {"run_id": run_id, "profile": profile, "sandbox": str(sandbox), "evidence": str(evidence),
            "backend": f"http://127.0.0.1:{port}", "port": port, "console": None, "env": env,
            "procs": [{"name": "backend", "pid": backend.pid}], "started_at": now()}
    _write_state(inst)
    try:
        _wait_http(inst["backend"] + "/health", backend, blog, timeout=180 if profile == "asr" else 60)
        if ui:
            ensure_console_deps(sandbox, log)
            cport = free_port()
            venv = dict(env, BACKEND_URL=inst["backend"])
            vlog = evidence / f"vite-{profile}.log"
            vcmd = ["node", str(sandbox / "console/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1",
                    "--port", str(cport), "--strictPort"]
            log("$ " + " ".join(vcmd) + "  (cwd sandbox/console, BACKEND_URL=backend)")
            vite = _spawn(vcmd, sandbox / "console", venv, vlog)
            inst["procs"].append({"name": "vite", "pid": vite.pid})
            inst["console"] = f"http://127.0.0.1:{cport}"
            _write_state(inst)
            _wait_http(inst["console"] + "/", vite, vlog, 60, ok=lambda r: r.status_code == 200 and "Safe Signal" in r.text)
    except BaseException:  # partial launch: stop what we started before the caller moves on
        stop(inst, log)
        raise
    return inst


def _write_state(inst: dict) -> None:
    STATE.write_text(json.dumps(inst, indent=1))


# --- doctor ------------------------------------------------------------------------------------

def _listening_pid_owns(pid: int, port: int) -> bool | None:
    """Does any process in pid's group own the LISTEN socket on port? None if /proc unreadable."""
    try:
        inodes = set()
        for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
            parts = line.split()
            if parts[3] == "0A" and int(parts[1].split(":")[1], 16) == port:
                inodes.add(parts[9])
        pids = [pid] + [int(p) for p in os.listdir("/proc") if p.isdigit() and _pgid(int(p)) == pid]
        for p in pids:
            for fd in Path(f"/proc/{p}/fd").iterdir():
                try:
                    link = os.readlink(fd)
                except OSError:
                    continue
                if link.startswith("socket:[") and link[8:-1] in inodes:
                    return True
        return False
    except OSError:
        return None


def _pgid(pid: int) -> int | None:
    try:
        return os.getpgid(pid)
    except OSError:
        return None


def doctor(inst: dict) -> list[dict]:
    """Read-only: is this instance worth driving? Returns [{name, ok, detail}]."""
    out = []

    def add(name, ok, detail):
        out.append({"name": name, "ok": bool(ok), "detail": detail})

    sandbox = inst["sandbox"]
    for p in inst["procs"]:
        add(f"proc-{p['name']}", _ours(p["pid"], sandbox), f"pid {p['pid']} alive with sandbox in cmdline")
    owns = _listening_pid_owns(inst["procs"][0]["pid"], inst["port"])
    add("port-owned", owns is not False, f"port {inst['port']} LISTEN socket owned by our backend"
        + (" (unverifiable: /proc unreadable)" if owns is None else ""))
    try:
        r = httpx.get(inst["backend"] + "/health", timeout=3)
        add("health", r.status_code == 200 and r.json().get("status") == "ok", f"/health -> {r.status_code}")
    except httpx.HTTPError as e:
        add("health", False, f"/health unreachable: {type(e).__name__}")
    db = Path(sandbox) / "data" / "safesignal.db"
    add("isolated-db", db.is_file(), f"app created its DB in the sandbox ({db.relative_to(HOME)})")
    try:
        with httpx.Client(base_url=inst["backend"], timeout=5) as c:
            r = c.post("/login", json={"password": inst["env"]["OPERATOR_PASSWORD"]})
            agg = c.get("/aggregates")
        add("auth", r.status_code == 200 and agg.status_code == 200,
            f"login {r.status_code}, cookie-authenticated /aggregates {agg.status_code}")
    except httpx.HTTPError as e:
        add("auth", False, f"login failed: {type(e).__name__}")
    if inst.get("console"):
        try:
            r = httpx.get(inst["console"] + "/health", timeout=5)
            add("console-proxy", r.status_code == 200, f"console {inst['console']} proxies /health -> {r.status_code}")
        except httpx.HTTPError as e:
            add("console-proxy", False, f"console unreachable: {type(e).__name__}")
    return out


def healthy(results: list[dict]) -> bool:
    return all(r["ok"] for r in results)


# --- cleanup -----------------------------------------------------------------------------------

def stop(inst: dict, log=print) -> None:
    """Kill only the process groups we started (verified by cmdline), then remove the sandbox.
    Never touches evidence."""
    for p in reversed(inst.get("procs", [])):
        pid = p["pid"]
        if not _ours(pid, inst["sandbox"]):
            continue
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
            except ProcessLookupError:
                break
            for _ in range(50):
                if not _ours(pid, inst["sandbox"]):
                    break
                time.sleep(0.1)
            else:
                continue
            break
        log(f"stopped {p['name']} (pgid {pid})")
    st = read_state()
    if st and st.get("run_id") == inst["run_id"]:
        STATE.unlink(missing_ok=True)


def remove_sandbox(sandbox: Path, log=print) -> None:
    sandbox = Path(sandbox).resolve()
    if SANDBOXES.resolve() not in sandbox.parents:  # only ever delete inside .verify/sandbox
        raise RuntimeError(f"refusing to delete {sandbox}: not under {SANDBOXES}")
    shutil.rmtree(sandbox, ignore_errors=True)
    log(f"removed sandbox {sandbox.relative_to(REPO) if REPO in sandbox.parents else sandbox}")


# --- user-data fingerprint (proves isolation) ---------------------------------------------------

def user_data_fingerprint() -> dict:
    """Hash + mtime of everything the app could write in the real checkout."""
    fp = {}
    for rel in ("data", "results"):
        root = REPO / rel
        if not root.exists():
            fp[rel] = None
            continue
        entries = {}
        for f in sorted(root.rglob("*")):
            if f.is_file():
                st = f.stat()
                entries[str(f.relative_to(REPO))] = [st.st_size, st.st_mtime_ns,
                                                     hashlib.sha256(f.read_bytes()).hexdigest()[:16]]
        fp[rel] = entries
    return fp
