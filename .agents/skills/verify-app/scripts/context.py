"""Drive context for checks: independent observers (SSE tap, SQLite read-back, API client),
a lazily-started Playwright browser, and the assertion/evidence recorder.

Outcome contract: a check ends PASS (every assertion held), FAIL (an assertion about the
app did not hold) or BLOCKED (a precondition or dependency was missing). Anything else
that goes wrong inside a check is reported as FAIL with category `harness-error`, never PASS.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
import time
from pathlib import Path

import httpx
import yaml

from harness import Blocked, now


class Fail(Exception):
    def __init__(self, reason: str, category: str = "app-behavior"):
        super().__init__(reason)
        self.category = category


class EventTap(threading.Thread):
    """Independent SSE subscriber on the backend (not through the console). Every event is
    appended to events-<profile>.jsonl with a receive timestamp."""

    def __init__(self, base: str, cookies: httpx.Cookies, path: Path):
        super().__init__(daemon=True)
        self.base, self.cookies, self.path = base, cookies, path
        self.events: list[dict] = []
        self.cond = threading.Condition()
        self.connected = threading.Event()
        self.error: str | None = None
        self._resp = None

    def run(self) -> None:
        try:
            with httpx.Client(base_url=self.base, cookies=self.cookies, timeout=httpx.Timeout(10, read=None)) as c:
                with c.stream("GET", "/events/stream") as r:
                    self._resp = r
                    if r.status_code != 200:
                        self.error = f"/events/stream -> HTTP {r.status_code}"
                        self.connected.set()
                        return
                    self.connected.set()
                    with open(self.path, "a") as out:
                        for line in r.iter_lines():
                            if not line.startswith("data: "):
                                continue
                            ev = json.loads(line[6:])
                            ev["_rx"] = now()
                            out.write(json.dumps(ev) + "\n")
                            out.flush()
                            with self.cond:
                                self.events.append(ev)
                                self.cond.notify_all()
        except Exception as e:  # stream closed at shutdown, or backend died
            self.error = self.error or f"{type(e).__name__}: {e}"
            self.connected.set()

    def close(self) -> None:
        try:
            if self._resp is not None:
                self._resp.close()
        except Exception:
            pass

    def mark(self) -> int:
        with self.cond:
            return len(self.events)

    def since(self, idx: int) -> list[dict]:
        with self.cond:
            return list(self.events[idx:])

    def wait_for(self, pred, since: int = 0, timeout: float = 30) -> dict | None:
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                for ev in self.events[since:]:
                    if pred(ev):
                        return ev
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self.cond.wait(left)


class Context:
    def __init__(self, inst: dict, evidence: Path, log):
        self.inst = inst
        self.env = inst["env"]
        self.sandbox = Path(inst["sandbox"])
        self.ev = evidence
        self.log = log
        self.rec: dict | None = None
        self.passed: set[str] = set()
        self._pw = self._browser = self.page = None
        self.templates = yaml.safe_load((self.sandbox / "policy/v1.0/templates.yaml").read_text())["templates"]
        self.api = self.anon = self.tap = None
        if not inst.get("backend"):  # cli profile: no server to observe
            return
        self.api = httpx.Client(base_url=inst["backend"], timeout=30)
        self.anon = httpx.Client(base_url=inst["backend"], timeout=30)
        r = self.api.post("/login", json={"password": self.env["OPERATOR_PASSWORD"]})
        if r.status_code != 200:
            raise Blocked(f"operator login for the observer client failed: HTTP {r.status_code}")
        self.tap = EventTap(inst["backend"], self.api.cookies, evidence / f"events-{inst['profile']}.jsonl")
        self.tap.start()
        if not self.tap.connected.wait(10) or self.tap.error:
            raise Blocked(f"SSE observer could not connect: {self.tap.error}")

    # --- recording -------------------------------------------------------------------------
    def expect(self, cond, what: str, observed=None) -> None:
        self.rec["assertions"].append({"what": what, "ok": bool(cond), "observed": _short(observed), "at": now()})
        if not cond:
            raise Fail(f"expected {what}; observed {_short(observed)}")

    def action(self, text: str) -> None:
        self.rec["actions"].append({"at": now(), "do": text})
        self.log(f"    · {text}")

    def artifact(self, path: Path) -> None:
        self.rec["evidence"].append(str(path.relative_to(self.ev)))

    def save_json(self, name: str, data) -> Path:
        p = self.ev / "artifacts" / f"{self.rec['id']}--{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=1, default=str))
        self.artifact(p)
        return p

    def shot(self, name: str) -> None:
        if self.page is None:
            return
        base = self.ev / "screenshots" / f"{self.rec['id']}--{name}"
        base.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(base) + ".png", full_page=True)
        self.artifact(Path(str(base) + ".png"))
        try:
            Path(str(base) + ".aria.txt").write_text(self.page.locator("body").aria_snapshot())
            self.artifact(Path(str(base) + ".aria.txt"))
        except Exception:
            pass

    # --- independent read-back ------------------------------------------------------------
    def db_rows(self, sql: str, args=()) -> list[tuple]:
        db = self.sandbox / "data" / "safesignal.db"
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    def phone_hash(self, phone: str) -> str:
        """Computed independently from the documented scheme: HMAC-SHA256(key=CONSENT_SALT, "consent-phone:" + E.164)."""
        return hmac.new(self.env["CONSENT_SALT"].encode(), b"consent-phone:" + phone.encode(), hashlib.sha256).hexdigest()

    def consent_db(self, phone: str | None = None) -> str | None:
        rows = self.db_rows("SELECT state FROM consent WHERE phone_hash = ?", (self.phone_hash(phone or self.env["DEMO_PHONE"]),))
        return rows[0][0] if rows else None

    def reply_count(self, keyword: str) -> int:
        return self.db_rows("SELECT COALESCE(SUM(count), 0) FROM reply_counts WHERE keyword = ?", (keyword,))[0][0]

    def outbox(self) -> list[dict]:
        r = self.api.get("/sms/outbox")
        if r.status_code != 200:
            raise Fail(f"GET /sms/outbox -> {r.status_code}")
        return r.json()

    # --- common operator steps (API) -----------------------------------------------------
    def api_reset(self) -> None:
        """Baseline for a journey: simulated SMS mode (reset never changes the mode) + reset."""
        mark = self.tap.mark()
        r = self.api.post("/demo/sms-mode", json={"mode": "simulated"})
        self.expect(r.status_code == 200 and r.json() == {"mode": "simulated"}, "precondition: SMS mode simulated", r.text)
        self.expect(self.api.post("/demo/reset").status_code == 200, "POST /demo/reset -> 200")
        self.wait_event(lambda e: e["type"] == "session" and e["payload"]["state"] == "reset", mark, 10, "session reset event")

    def api_reply(self, body: str) -> dict:
        r = self.api.post("/sms/simulate-inbound", json={"body": body})
        self.expect(r.status_code == 200, f"POST /sms/simulate-inbound {body!r} -> 200", r.status_code)
        return r.json()

    def ensure_opted_in(self) -> None:
        if self.consent_db() != "active":
            self.action("precondition: opt the demo phone in by replying YES")
            self.api_reply("YES")
        self.expect(self.consent_db() == "active", "demo phone consent is active in SQLite", self.consent_db())

    def wait_event(self, pred, since: int, timeout: float, what: str) -> dict:
        ev = self.tap.wait_for(pred, since, timeout)
        self.expect(ev is not None, f"SSE {what} within {timeout:.0f}s",
                    [(e["type"], e["payload"].get("state") or e["payload"].get("template_id") or e["payload"].get("seq"))
                     for e in self.tap.since(since)][-12:])
        return ev

    # --- browser ---------------------------------------------------------------------------
    def browser_page(self, fresh_context: bool = False):
        if not self.inst.get("console"):
            raise Blocked("check needs the console but the instance was launched without --ui")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise Blocked("python playwright not importable; run via `make verify` "
                          "(uv run --with playwright==1.64.1)") from None
        if self._pw is None:
            self._pw = sync_playwright().start()
            try:
                # Fake mic for live.mic-ui: auto-grants getUserMedia and loops the bank call's code request.
                wav = self.sandbox / "audio/demo/bank/t04.wav"
                self._browser = self._pw.chromium.launch(headless=True, args=[
                    "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                    f"--use-file-for-fake-audio-capture={wav}"])
            except Exception as e:
                raise Blocked(f"chromium for playwright 1.64.1 not installed ({str(e).splitlines()[0]}); "
                              "run `uv run --with playwright==1.64.1 playwright install chromium`") from None
        if fresh_context:
            ctx = self._browser.new_context(viewport={"width": 1440, "height": 900}, permissions=["microphone"])
            return ctx.new_page()
        if self.page is None:
            ctx = self._browser.new_context(viewport={"width": 1440, "height": 900}, permissions=["microphone"])
            self.page = ctx.new_page()
            self.page.set_default_timeout(15_000)
        return self.page

    def close(self) -> None:
        if self.tap:
            self.tap.close()
        for c in (self.api, self.anon):
            if c:
                c.close()
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass


def _short(v, n: int = 400):
    if v is None or isinstance(v, (bool, int, float)):
        return v
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s if len(s) <= n else s[:n] + "…"
