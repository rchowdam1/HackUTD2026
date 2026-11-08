"""User journeys. Each check drives the real app through a user-facing path and asserts the
outcome through at least one channel other than the one it acted on (SSE observer, SQLite
read-back, operator API, files on disk, or the rendered console).

Registry fields: id, feature (features/<feature>.md), profile (cached | asr | cli),
ui (needs the Vite console + Playwright), requires (check ids that must PASS first in
this run, else BLOCKED), control (negative control: excluded unless --negative-control),
known_gap (issue ref for a documented product gap: an app-behavior FAIL is reported as
KNOWN-GAP and does not fail the verdict; a PASS is flagged so the marker gets removed).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from context import Context, Fail
from harness import Blocked, DEFAULT_HF_HOME, WHISPER_MODEL_DIR, sandbox_env

# Accessible names / visible strings the UI checks depend on. `verify.py lint` greps
# console/src for each one, so a renamed button shows up as verification drift.
UI_HANDLES = [
    "Operator password", "Log in", "Wrong password", "Run clinic", "Run bank", "Run grandson", "End call", "Reset",
    "SMS mode", "simulated SMS", "Live transcript", "cached transcript", "No call yet.",
    "Why this alert", "No alert detected", "Caller asked for a code", "Caught by", "CallSafe rules",
    "Start live conversation", "Caller", "tap to stop", "Live mic", "Transcribing...",
    "Caller said", "Why it matters", "Whoever has the code can get into your account", "We texted", "Speed",
    "fixture replay", "call ended", "call running", "No texts yet.",
    "Opt in to call monitoring?", "Alert message sent to user", "Follow-up message sent to user",
    "Monitoring opt-in: No. No text sent", "Call monitoring is off.",
]
# Routes the harness calls; lint checks each is still declared in backend/app.
API_ROUTES = ["/login", "/health", "/events/stream", "/demo/run/{scenario_id}", "/demo/end-call", "/demo/reset",
              "/demo/sms-mode", "/results/latest", "/aggregates", "/sms/simulate-inbound", "/sms/outbox",
              "/sms/invite", "/sms/inbound", "/sms/status", "/sms/templates/{template_id}", "/sms/consent",
              "/live/start", "/live/utterance", "/voice/incoming", "/voice/stream"]


@dataclass
class Check:
    id: str
    feature: str
    profile: str
    ui: bool
    fn: object
    requires: list[str] = field(default_factory=list)
    control: bool = False
    known_gap: str = ""


CHECKS: list[Check] = []


def check(id, feature, profile="cached", ui=False, requires=(), control=False, known_gap=""):
    def deco(fn):
        CHECKS.append(Check(id, feature, profile, ui, fn, list(requires), control, known_gap))
        return fn
    return deco


# --- UI helpers ------------------------------------------------------------------------------

def pw_expect():
    from playwright.sync_api import expect
    return expect


def ui_assert(ctx: Context, what: str, fn) -> None:
    """Run a Playwright web-first assertion and record it."""
    try:
        fn()
        ctx.expect(True, what)
    except AssertionError as e:
        msg = " ".join(str(e).split())[:400]
        if "element(s) not found" in msg:  # the handle is gone: UI regression or map drift, not a wrong value
            ctx.rec["assertions"].append({"what": what, "ok": False, "observed": msg})
            raise Fail(f"UI handle for '{what}' not found - UI regression OR verification drift "
                       f"(run `verify.py lint`, check the screenshot): {msg[:200]}", "ui-locator") from None
        ctx.expect(False, what, msg)


def card(page, heading_pattern: str):
    """A console card (`.card`: <section> or <div>) identified by its H2 text."""
    return page.locator(".card").filter(has=page.get_by_role("heading", name=re.compile(heading_pattern)))


def dd(section, term: str):
    return section.locator("dt", has_text=term).locator("xpath=following-sibling::dd[1]")


def open_console(ctx: Context):
    """Logged-in console page with a fresh reducer and a *proven* live SSE stream.

    The Vite proxy withholds the stream's response headers until the first event, so the
    browser's `response`/`onopen` can't signal readiness. Instead: reset (harmless: never
    touches consent or counts) until the banner shows "reset", which only an SSE event can do.
    """
    page = ctx.browser_page()
    page.goto(ctx.inst["console"] + "/")
    page.wait_for_selector("form.login, .console", timeout=15_000)
    login = page.get_by_placeholder("Operator password")
    if login.count():
        ctx.action("log in through the console form")
        login.fill(ctx.env["OPERATOR_PASSWORD"])
        page.get_by_role("button", name="Log in").click()
        # Every login asks; keep the consent the check set up (No turns invited into stopped).
        answer_opt_in(ctx, page, "Yes" if ctx.consent_db() == "active" else "No")
    page.get_by_role("button", name="Run bank").wait_for()
    banner = page.get_by_role("banner")
    for _ in range(20):
        ctx.api.post("/demo/reset")
        try:
            banner.get_by_text("reset", exact=True).wait_for(timeout=500)
            return page
        except Exception:
            continue
    raise Fail("console never received a live SSE event (reset not reflected within 10 s)", "ui-stream")


def opt_in_dialog(page):
    return page.get_by_role("dialog", name="Opt in to call monitoring?")


def answer_opt_in(ctx: Context, page, choice: str) -> None:
    """Click Yes/No in the after-login prompt and wait for POST /sms/consent and the dialog to close."""
    dialog = opt_in_dialog(page)
    dialog.wait_for()
    ctx.action(f"answer the opt-in prompt: {choice}")
    with page.expect_response(lambda r: r.url.endswith("/sms/consent")) as resp:
        dialog.get_by_role("button", name=choice, exact=True).click()
    ctx.expect(resp.value.status == 200, f"opt-in {choice}: POST /sms/consent -> 200", resp.value.status)
    dialog.wait_for(state="hidden")


def click(ctx: Context, page, name: str, scope=None):
    ctx.action(f"click button {name!r}")
    (scope or page).get_by_role("button", name=name, exact=True).click()


def transcript_lines(ctx: Context, scenario: str) -> list[dict]:
    return json.loads((ctx.sandbox / "scenarios/demo" / scenario / "transcript.json").read_text())


def events_for(ctx: Context, since: int, ref: str, type_: str | None = None) -> list[dict]:
    return [e for e in ctx.tap.since(since) if e.get("session_ref") == ref and (type_ is None or e["type"] == type_)]


def start_replay_ui(ctx: Context, page, button: str, since: int) -> tuple[str, float]:
    click(ctx, page, button)
    t0 = time.monotonic()
    ev = ctx.wait_event(lambda e: e["type"] == "session" and e["payload"]["state"] == "running", since, 10,
                        "session running")
    return ev["session_ref"], t0


# --- operator-login ---------------------------------------------------------------------------

PROTECTED = [("GET", "/aggregates"), ("GET", "/results/latest"), ("GET", "/sms/outbox"), ("GET", "/events/stream"),
             ("POST", "/demo/run/bank"), ("POST", "/demo/end-call"), ("POST", "/demo/reset"),
             ("POST", "/demo/sms-mode"), ("POST", "/sms/simulate-inbound"), ("POST", "/sms/invite"),
             ("GET", "/sms/templates/R-HELP"), ("POST", "/sms/consent")]


@check("login.api-guard", "operator-login")
def login_api_guard(ctx: Context):
    mark = ctx.tap.mark()
    for method, path in PROTECTED:
        r = ctx.anon.request(method, path, json={} if method == "POST" else None)
        ctx.expect(r.status_code == 401, f"{method} {path} without cookie -> 401", r.status_code)
    r = ctx.anon.get("/health")
    ctx.expect(r.status_code == 200 and r.json() == {"status": "ok"}, "GET /health is public and ok", r.text)
    r = ctx.anon.post("/login", json={"password": "not-the-password"})
    ctx.expect(r.status_code == 401 and "set-cookie" not in r.headers, "wrong password -> 401 and no cookie",
               [r.status_code, r.headers.get("set-cookie")])
    r = ctx.anon.get("/aggregates", cookies={"safesignal_session": "forged.deadbeef"})
    ctx.expect(r.status_code == 401, "forged session cookie -> 401", r.status_code)
    time.sleep(1)
    ctx.expect(not [e for e in ctx.tap.since(mark) if e["type"] == "session"],
               "unauthenticated POST /demo/run/bank started no session (SSE)", ctx.tap.since(mark))


@check("login.ui-wrong-password", "operator-login", ui=True)
def login_ui_wrong(ctx: Context):
    page = ctx.browser_page(fresh_context=True)
    try:
        page.goto(ctx.inst["console"] + "/")
        ctx.action("type a wrong password and submit")
        page.get_by_placeholder("Operator password").fill("wrong-" + uuid.uuid4().hex[:6])
        page.get_by_role("button", name="Log in").click()
        ui_assert(ctx, "'Wrong password' error shown", lambda: pw_expect()(page.get_by_text("Wrong password")).to_be_visible())
        ui_assert(ctx, "console controls not rendered", lambda: pw_expect()(page.get_by_role("button", name="Run bank")).to_have_count(0))
        ctx.expect(not page.context.cookies(), "no session cookie stored", page.context.cookies())
        base = ctx.ev / "screenshots" / f"{ctx.rec['id']}--wrong-password.png"
        base.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(base))
        ctx.artifact(base)
    finally:
        page.context.close()


@check("login.ui-success", "operator-login", ui=True)
def login_ui_success(ctx: Context):
    page = ctx.browser_page()
    page.context.clear_cookies()
    page.goto(ctx.inst["console"] + "/")
    ctx.action("type the operator password and submit")
    page.get_by_placeholder("Operator password").fill(ctx.env["OPERATOR_PASSWORD"])
    page.get_by_role("button", name="Log in").click()
    ui_assert(ctx, "operator console rendered (Run bank button)", lambda: pw_expect()(page.get_by_role("button", name="Run bank")).to_be_visible())
    ui_assert(ctx, "opt-in prompt shown after login", lambda: pw_expect()(opt_in_dialog(page)).to_be_visible())
    answer_opt_in(ctx, page, "Yes" if ctx.consent_db() == "active" else "No")  # keep consent as the run had it
    cookies = {c["name"]: c for c in page.context.cookies()}
    c = cookies.get("safesignal_session")
    ctx.expect(c and c["httpOnly"] and c["sameSite"] == "Strict", "session cookie is HttpOnly + SameSite=Strict", c)
    r = page.request.get(ctx.inst["console"] + "/aggregates")
    ctx.expect(r.status == 200, "browser cookie authenticates /aggregates through the console proxy", r.status)
    ctx.shot("logged-in")


@check("login.opt-in-every-login", "operator-login", ui=True)
def login_opt_in(ctx: Context):
    ctx.ensure_opted_in()  # start active so both answers below are observable transitions
    page = ctx.browser_page(fresh_context=True)
    try:
        for choice, state in (("No", "stopped"), ("Yes", "active")):
            page.context.clear_cookies()
            page.goto(ctx.inst["console"] + "/")
            ctx.action(f"log in through the console form (then choose {choice})")
            page.get_by_placeholder("Operator password").fill(ctx.env["OPERATOR_PASSWORD"])
            page.get_by_role("button", name="Log in").click()
            ui_assert(ctx, f"opt-in prompt shown on this login ({choice} run)", lambda: pw_expect()(opt_in_dialog(page)).to_be_visible())
            shot = ctx.ev / "screenshots" / f"{ctx.rec['id']}--prompt-{choice.lower()}.png"
            shot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(shot))
            ctx.artifact(shot)
            out0, mark = len(ctx.outbox()), ctx.tap.mark()
            answer_opt_in(ctx, page, choice)
            ctx.wait_event(lambda e: e["type"] == "consent" and e["payload"]["state"] == state, mark, 10,
                           f"consent {state} event after {choice}")
            ctx.expect(ctx.consent_db() == state, f"{choice} stores consent {state} (SQLite)", ctx.consent_db())
            ctx.expect(len(ctx.outbox()) == out0, f"{choice} sends no text", ctx.outbox()[out0:])
        ctx.action("reload the page (same login)")
        page.reload()
        page.get_by_role("button", name="Run bank").wait_for()
        ui_assert(ctx, "no prompt on a reload within the same login", lambda: pw_expect()(opt_in_dialog(page)).to_have_count(0))
    finally:
        page.context.close()


# --- fixture-replay ---------------------------------------------------------------------------

@check("fixtures.console-replay", "fixture-replay", ui=True)
def fixtures_replay(ctx: Context):
    seg = json.loads((ctx.sandbox / "tests/fixtures/events/segment.json").read_text())["payload"]["text"]
    page = ctx.browser_page(fresh_context=True)
    backend_calls = []
    api = re.compile(r"^/(events/stream|aggregates|results/|demo/|login|sms/)")  # not /@fs/.../tests/fixtures/events/*
    page.on("request", lambda r: backend_calls.append(r.url) if api.match(urlparse(r.url).path) else None)
    try:
        ctx.action("open the console with ?fixtures (no login)")
        page.goto(ctx.inst["console"] + "/?fixtures")
        ui_assert(ctx, "'fixture replay' tag shown", lambda: pw_expect()(page.get_by_text("fixture replay")).to_be_visible())
        ui_assert(ctx, "Run bank disabled in fixture mode", lambda: pw_expect()(page.get_by_role("button", name="Run bank")).to_be_disabled())
        ui_assert(ctx, "fixture segment text appears in the transcript",
                  lambda: pw_expect()(card(page, "^Live transcript")).to_contain_text(seg, timeout=15_000))
        ctx.expect(not backend_calls, "fixture mode made no backend API calls", backend_calls)
        shot = ctx.ev / "screenshots" / f"{ctx.rec['id']}--fixtures.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(shot), full_page=True)
        ctx.artifact(shot)
    finally:
        page.context.close()


# --- results-card -----------------------------------------------------------------------------

@check("results.pending", "results-card")
def results_pending(ctx: Context):
    f = ctx.sandbox / "results/latest.json"
    if f.exists():
        ctx.action("move the sandbox's committed results/latest.json aside to observe the pending state")
        f.rename(f.with_suffix(".json.verify-aside"))
    r = ctx.api.get("/results/latest")
    ctx.expect(r.status_code == 200 and r.json() == {"status": "pending"}, "GET /results/latest -> 200 {status: pending}", r.text)


@check("results.eval-cli-to-api", "results-card", profile="cached")
def results_eval(ctx: Context):
    cmd = [sys.executable, "-m", "eval.run", "--arms", "K,B", "--batch", "dev"]
    ctx.action("$ " + " ".join(cmd[1:]) + "  (cwd sandbox)")
    p = subprocess.run(cmd, cwd=ctx.sandbox, env=ctx.env, capture_output=True, text=True, timeout=120)
    (ctx.ev / "artifacts").mkdir(exist_ok=True)
    out = ctx.ev / "artifacts" / f"{ctx.rec['id']}--eval-stdout.txt"
    out.write_text(f"$ {' '.join(cmd)}\nexit {p.returncode}\n--- stdout\n{p.stdout}\n--- stderr\n{p.stderr}")
    ctx.artifact(out)
    ctx.expect(p.returncode == 0, "eval CLI exits 0", p.returncode)
    f = ctx.sandbox / "results/latest.json"
    ctx.expect(f.is_file(), "eval wrote results/latest.json in the sandbox", str(f))
    raw = f.read_bytes()
    data = json.loads(raw)
    ctx.save_json("latest", data)
    ctx.expect(data.get("batch") == "dev" and {"K", "B"} <= set(data.get("arms", {})), "results cover batch dev, arms K and B", data)
    r = ctx.api.get("/results/latest")
    ctx.expect(r.content == raw, "GET /results/latest returns the file byte-for-byte", r.text[:200])


# --- call-replay ------------------------------------------------------------------------------

@check("replay.clinic-silent", "call-replay", ui=True)
def replay_clinic(ctx: Context):
    ctx.api_reset()
    ctx.ensure_opted_in()  # opted in, so "No texts yet." proves silence rather than monitoring off
    page = open_console(ctx)
    expected = transcript_lines(ctx, "clinic")
    out0, mark = len(ctx.outbox()), ctx.tap.mark()
    ref, _ = start_replay_ui(ctx, page, "Run clinic", mark)
    run = events_for(ctx, mark, ref, "session")[0]["payload"]
    ctx.expect(run["arm"] == "B" and run["sms_mode"] == "simulated", "session runs arm B in simulated SMS mode", run)
    ui_assert(ctx, "status shows 'call running · rules only'",
              lambda: pw_expect()(page.get_by_role("banner")).to_contain_text("call running · rules only"))
    ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "session" and e["payload"]["state"] == "finished",
                   mark, 40, "session finished (auto end-call after last turn)")
    segs = [e["payload"] for e in events_for(ctx, mark, ref, "segment")]
    ctx.expect([(s["seq"], s["text"], s["source"]) for s in segs] == [(x["seq"], x["text"], "cached") for x in expected],
               "SSE segments equal scenarios/demo/clinic/transcript.json, source cached", segs)
    ctx.expect(not events_for(ctx, mark, ref, "decision"), "no decision for the clinic call", events_for(ctx, mark, ref, "decision"))
    ctx.expect(not events_for(ctx, mark, ref, "sms"), "no SMS event for the clinic call", events_for(ctx, mark, ref, "sms"))
    ctx.expect(len(ctx.outbox()) == out0, "simulated outbox unchanged (phone stays silent)", len(ctx.outbox()) - out0)
    tr = card(page, "^Live transcript")
    for x in expected:
        ui_assert(ctx, f"transcript shows turn {x['seq']}", lambda: pw_expect()(tr).to_contain_text(x["text"]))
    ui_assert(ctx, "transcript labelled 'cached transcript'", lambda: pw_expect()(tr.get_by_text("cached transcript")).to_be_visible())
    ui_assert(ctx, "status shows 'call ended'", lambda: pw_expect()(page.get_by_role("banner")).to_contain_text("call ended"))
    ui_assert(ctx, "Why panel: 'No alert detected'",
              lambda: pw_expect()(card(page, "^Why this alert")).to_contain_text("No alert detected"))
    ui_assert(ctx, "phone frame shows no texts", lambda: pw_expect()(card(page, "^Phone")).to_contain_text("No texts yet."))
    ui_assert(ctx, "no SMS marker in the transcript", lambda: pw_expect()(tr.locator("p.marker")).to_have_count(0))
    ctx.shot("clinic-finished")


@check("replay.grandson-rules-only", "call-replay", ui=True)
def replay_grandson(ctx: Context):
    ctx.api_reset()
    ctx.ensure_opted_in()
    page = open_console(ctx)
    expected = transcript_lines(ctx, "family")
    out0, mark = len(ctx.outbox()), ctx.tap.mark()
    ref, _ = start_replay_ui(ctx, page, "Run grandson", mark)
    run = events_for(ctx, mark, ref, "session")[0]["payload"]
    ctx.expect(run["arm"] == "B", "no OpenRouter key in the sandbox: the session runs arm B (rules only)", run)
    ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "session" and e["payload"]["state"] == "finished",
                   mark, 45, "session finished (auto end-call after last turn)")
    segs = [e["payload"] for e in events_for(ctx, mark, ref, "segment")]
    ctx.expect([(s["seq"], s["text"], s["source"]) for s in segs] == [(x["seq"], x["text"], "cached") for x in expected],
               "SSE segments equal scenarios/demo/family/transcript.json, source cached", segs)
    ctx.expect(not events_for(ctx, mark, ref, "decision"), "the rules alone raise no decision (the model is what catches it)",
               events_for(ctx, mark, ref, "decision"))
    ctx.expect(len(ctx.outbox()) == out0, "simulated outbox unchanged", len(ctx.outbox()) - out0)
    tr = card(page, "^Live transcript")
    for x in expected:
        ui_assert(ctx, f"transcript shows turn {x['seq']}", lambda: pw_expect()(tr).to_contain_text(x["text"]))
    ui_assert(ctx, "Why panel: 'No alert detected'",
              lambda: pw_expect()(card(page, "^Why this alert")).to_contain_text("No alert detected"))
    ctx.shot("grandson-finished")


@check("replay.bank-alert", "call-replay", ui=True)
def replay_bank(ctx: Context):
    ctx.api_reset()
    ctx.ensure_opted_in()
    page = open_console(ctx)
    expected = transcript_lines(ctx, "bank")
    out0, mark = len(ctx.outbox()), ctx.tap.mark()
    ref, t0 = start_replay_ui(ctx, page, "Run bank", mark)
    dec = ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "decision", mark, 35, "decision")["payload"]
    ctx.expect(dec["level"] == "action_warning" and dec["template_id"] == "ALERT-OTP-01"
               and dec["followup_template_id"] == "FU-OTP-01", "decision is ALERT-OTP-01 with follow-up FU-OTP-01", dec)
    ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "session" and e["payload"]["state"] == "finished",
                   mark, 40, "session finished (auto end-call)")
    evs = events_for(ctx, mark, ref)
    segs = [e["payload"] for e in evs if e["type"] == "segment"]
    ctx.expect([(s["seq"], s["text"], s["source"]) for s in segs] == [(x["seq"], x["text"], "cached") for x in expected],
               "SSE segments equal scenarios/demo/bank/transcript.json, source cached", segs)
    order = [(e["type"], e["payload"].get("template_id") or e["payload"].get("state")) for e in evs
             if e["type"] in ("sms", "session")]
    ctx.save_json("event-order", order)
    ctx.expect(order == [("session", "running"), ("sms", "ALERT-OTP-01"), ("sms", "FU-OTP-01"), ("session", "finished")],
               "ordering: running -> ALERT sms -> exactly one FU sms -> finished", order)
    sms = [e["payload"] for e in evs if e["type"] == "sms"]
    ctx.expect(all(s["status"] == "queued" and s["message_id"] for s in sms), "both SMS queued with message ids", sms)
    risks = [e["payload"] for e in evs if e["type"] == "risk_event"]
    ctx.expect(dec["basis"] and set(dec["basis"]) <= {r["rule_id"] for r in risks},
               "decision basis cites rule ids of published risk events", [dec["basis"], risks])
    ctx.expect(all(r["category"] == "otp" for r in risks if r["rule_id"] in dec["basis"]), "cited risk category is otp", risks)
    new = ctx.outbox()[out0:]
    ctx.save_json("outbox-new", new)
    ctx.expect([m["template_id"] for m in new] == ["ALERT-OTP-01", "FU-OTP-01"],
               "outbox gained exactly ALERT-OTP-01 then FU-OTP-01", new)
    ctx.expect(all(m["text"] == ctx.templates[m["template_id"]] for m in new), "texts equal policy/v1.0/templates.yaml", new)
    ctx.expect(all(m["message_id"] in {s["message_id"] for s in sms} for m in new), "outbox ids match SSE sms ids", [new, sms])
    risk = next(r for r in risks if r["rule_id"] in dec["basis"])
    tr, why, phone = card(page, "^Live transcript"), card(page, "^Why this alert"), card(page, "^Phone")
    for x in expected:
        ui_assert(ctx, f"transcript shows turn {x['seq']}", lambda: pw_expect()(tr).to_contain_text(x["text"]))
    ui_assert(ctx, "Why panel headline 'Caller asked for a code'", lambda: pw_expect()(why).to_contain_text("Caller asked for a code"))
    ctx.expect(risk["source"] == "rule" and risk["score"] is None, "the cited risk event is a rule hit (no model score)", risk)
    ui_assert(ctx, "Why panel 'Caught by' = 'CallSafe rules'", lambda: pw_expect()(dd(why, "Caught by")).to_have_text("CallSafe rules"))
    flagged = next(s["text"] for s in segs if s["seq"] == risk["span_seq"][-1])
    ui_assert(ctx, "Why panel 'Caller said' quotes the flagged line",
              lambda: pw_expect()(dd(why, "Caller said")).to_have_text(f"“{flagged}”"))
    spans = [flagged[a:b] for a, b in risk["match_spans"]]
    ctx.expect(bool(spans), "the cited rule event carries match_spans", risk)
    ui_assert(ctx, f"Why panel highlights exactly the matched words {spans}",
              lambda: pw_expect()(dd(why, "Caller said").locator("mark")).to_have_text(spans))
    ui_assert(ctx, "Why panel 'Why it matters' explains the code risk",
              lambda: pw_expect()(dd(why, "Why it matters")).to_contain_text("Whoever has the code can get into your account"))
    told = re.sub(r"^CallSafe:\s*(\w)", lambda m: m.group(1).upper(), ctx.templates["ALERT-OTP-01"])
    ui_assert(ctx, "Why panel 'We texted' = the ALERT-OTP-01 template text",
              lambda: pw_expect()(dd(why, "We texted")).to_have_text(told))
    ui_assert(ctx, "Why panel 'Speed' shows the measured ms",
              lambda: pw_expect()(dd(why, "Speed")).to_have_text(re.compile(r"^Alert went out \d+ ms after the line came in$")))
    for tid in ("ALERT-OTP-01", "FU-OTP-01"):
        ui_assert(ctx, f"phone frame shows {tid} text", lambda: pw_expect()(phone).to_contain_text(ctx.templates[tid]))
    ui_assert(ctx, "transcript marker '* Alert message sent to user' right after the flagged line",
              lambda: pw_expect()(tr.locator("p.line.flagged + p.marker")).to_have_text("* Alert message sent to user"))
    ui_assert(ctx, "exactly two markers: alert, then '* Follow-up message sent to user'",
              lambda: pw_expect()(tr.locator("p.marker")).to_have_text(["* Alert message sent to user", "* Follow-up message sent to user"]))
    ui_assert(ctx, "status shows 'call ended'", lambda: pw_expect()(page.get_by_role("banner")).to_contain_text("call ended"))
    ctx.rec["timing"] = {"replay_wall_s": round(time.monotonic() - t0, 1)}
    ctx.shot("bank-finished")


# --- sms-replies ------------------------------------------------------------------------------

@check("replies.opt-in-yes", "sms-replies", ui=True)
def replies_yes(ctx: Context):
    ctx.action("precondition: reply STOP via the API so the YES transition is observable")
    ctx.api_reply("STOP")
    ctx.expect(ctx.consent_db() == "stopped", "consent stopped in SQLite before YES", ctx.consent_db())
    page = open_console(ctx)
    mark = ctx.tap.mark()
    click(ctx, page, "YES", card(page, "^Phone"))
    rep = ctx.wait_event(lambda e: e["type"] == "reply", mark, 10, "reply event")["payload"]
    ctx.expect(rep["keyword"] == "YES", "reply keyword YES", rep)
    con = ctx.wait_event(lambda e: e["type"] == "consent", mark, 10, "consent event")["payload"]
    ctx.expect(con["state"] == "active", "consent event active", con)
    ctx.expect(ctx.consent_db() == "active", "SQLite consent row (HMAC of DEMO_PHONE) is active", ctx.consent_db())
    last = ctx.outbox()[-1]
    ctx.expect(last["template_id"] == "R-YES", "outbox last message is R-YES", last)
    ui_assert(ctx, "phone frame shows R-YES text", lambda: pw_expect()(card(page, "^Phone")).to_contain_text(ctx.templates["R-YES"]))
    ctx.shot("opted-in")


@check("replies.wrong-counter", "sms-replies", ui=True, requires=["replay.bank-alert"])
def replies_wrong(ctx: Context):
    page = open_console(ctx)
    n = ctx.reply_count("WRONG")
    mark = ctx.tap.mark()
    click(ctx, page, "WRONG", card(page, "^Phone"))
    rep = ctx.wait_event(lambda e: e["type"] == "reply", mark, 10, "reply event")["payload"]
    ctx.expect(rep == {"keyword": "WRONG", "counted": True, "wrong_count": n + 1}, "reply WRONG counted, wrong_count n+1", rep)
    ctx.expect(ctx.reply_count("WRONG") == n + 1, "SQLite reply_counts WRONG total is n+1", ctx.reply_count("WRONG"))
    rows = ctx.db_rows("SELECT template_id, count FROM reply_counts WHERE keyword='WRONG'")
    ctx.expect(any(t == "ALERT-OTP-01" for t, _ in rows), "count attributed to the latest alert ALERT-OTP-01", rows)
    agg = ctx.api.get("/aggregates").json()
    ctx.expect(sum(r["count"] for r in agg["replies"] if r["keyword"] == "WRONG") == n + 1, "GET /aggregates agrees", agg)
    ctx.expect(ctx.outbox()[-1]["template_id"] == "R-WRONG", "outbox last message is R-WRONG", ctx.outbox()[-1])
    ui_assert(ctx, "phone frame shows the WRONG reply bubble", lambda: pw_expect()(card(page, "^Phone").locator(".bubble.in").last).to_have_text("WRONG"))
    ctx.shot("wrong-counted")


@check("replies.shared", "sms-replies", ui=True, requires=["replay.bank-alert"])
def replies_shared(ctx: Context):
    page = open_console(ctx)
    mark = ctx.tap.mark()
    click(ctx, page, "SHARED", card(page, "^Phone"))
    rep = ctx.wait_event(lambda e: e["type"] == "reply", mark, 10, "reply event")["payload"]
    ctx.expect(rep["keyword"] == "SHARED" and rep["counted"], "reply SHARED, counted", rep)
    ctx.expect(ctx.outbox()[-1]["template_id"] == "R-SHARED-OTP", "category-specific R-SHARED-OTP sent", ctx.outbox()[-1])
    ui_assert(ctx, "phone frame shows R-SHARED-OTP text",
              lambda: pw_expect()(card(page, "^Phone")).to_contain_text(ctx.templates["R-SHARED-OTP"]))
    ctx.shot("shared")


@check("replies.keyword-normalise", "sms-replies")
def replies_normalise(ctx: Context):
    cases = [("  wrong. ", "WRONG", "R-WRONG"), ("Hello?", "HELP", "R-HELP"), ("Stop please!", "STOP", "R-STOP"),
             ("yes", "YES", "R-YES")]
    for body, kw, tid in cases:
        rep = ctx.api_reply(body)
        ctx.expect(rep["keyword"] == kw, f"{body!r} normalises to {kw}", rep)
        ctx.expect(ctx.outbox()[-1]["template_id"] == tid, f"{body!r} answered with {tid}", ctx.outbox()[-1])
        if kw == "STOP":
            ctx.expect(ctx.consent_db() == "stopped", "STOP variant stops consent (SQLite)", ctx.consent_db())
    ctx.expect(ctx.consent_db() == "active", "final YES re-activates consent (SQLite)", ctx.consent_db())


@check("replies.stop-blocks-alerts", "sms-replies", ui=True)
def replies_stop(ctx: Context):
    ctx.api_reset()
    ctx.ensure_opted_in()
    page = open_console(ctx)
    phone = card(page, "^Phone")
    mark = ctx.tap.mark()
    click(ctx, page, "STOP", phone)
    ctx.wait_event(lambda e: e["type"] == "consent" and e["payload"]["state"] == "stopped", mark, 10, "consent stopped event")
    ctx.expect(ctx.consent_db() == "stopped", "SQLite consent stopped", ctx.consent_db())
    ctx.expect(ctx.outbox()[-1]["template_id"] == "R-STOP", "simulated phone receives R-STOP", ctx.outbox()[-1])
    try:
        out0, mark = len(ctx.outbox()), ctx.tap.mark()
        ref, _ = start_replay_ui(ctx, page, "Run bank", mark)
        ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "session" and e["payload"]["state"] == "finished",
                       mark, 40, "session finished")
        evs = events_for(ctx, mark, ref)
        ctx.expect([e["payload"]["template_id"] for e in evs if e["type"] == "decision"] == ["ALERT-OTP-01"],
                   "rules still decide ALERT-OTP-01", evs)
        sms = [e["payload"] for e in evs if e["type"] == "sms"]
        ctx.expect(sms == [], "opted out: alert skipped, no sms event (not 'failed'), no follow-up", sms)
        ctx.expect(len(ctx.outbox()) == out0, "nothing reached the simulated phone", ctx.outbox()[out0:])
        why = card(page, "^Why this alert")
        ui_assert(ctx, "Why panel still explains the alert", lambda: pw_expect()(why).to_contain_text("Caller asked for a code"))
        ui_assert(ctx, "Why panel says 'Monitoring opt-in: No. No text sent'",
                  lambda: pw_expect()(why).to_contain_text("Monitoring opt-in: No. No text sent"))
        ui_assert(ctx, "nothing reads as failed", lambda: pw_expect()(page.locator("main")).not_to_contain_text("failed"))
        ui_assert(ctx, "phone says 'Call monitoring is off.'", lambda: pw_expect()(phone).to_contain_text("Call monitoring is off."))
        ui_assert(ctx, "no SMS marker in the transcript",
                  lambda: pw_expect()(card(page, "^Live transcript").locator("p.marker")).to_have_count(0))
        ctx.shot("stopped-alert-skipped")
    finally:
        ctx.action("restore consent: reply YES")
        click(ctx, page, "YES", phone)
        deadline = time.monotonic() + 5
        while ctx.consent_db() != "active" and time.monotonic() < deadline:
            time.sleep(0.2)
    ctx.expect(ctx.consent_db() == "active", "consent restored to active", ctx.consent_db())


# --- call-controls ----------------------------------------------------------------------------

@check("controls.end-call-midway", "call-controls", ui=True)
def controls_end_call(ctx: Context):
    ctx.api_reset()
    ctx.ensure_opted_in()
    page = open_console(ctx)
    out0, mark = len(ctx.outbox()), ctx.tap.mark()
    ref, t0 = start_replay_ui(ctx, page, "Run bank", mark)
    ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "segment", mark, 15, "first segment")
    click(ctx, page, "End call")
    fin = ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "session" and e["payload"]["state"] == "finished",
                         mark, 10, "session finished after End call")
    ctx.action("wait past the replay's natural end (≈8 s) for late events")
    time.sleep(max(0.0, 10 - (time.monotonic() - t0)))
    evs = events_for(ctx, mark, ref)
    after = evs[evs.index(fin) + 1:]
    ctx.expect(not after, "no events for the call after it finished", after)
    ctx.expect(len([e for e in evs if e["type"] == "segment"]) < 4, "replay stopped before the OTP request turn",
               [e["payload"]["seq"] for e in evs if e["type"] == "segment"])
    ctx.expect(not [e for e in evs if e["type"] in ("decision", "sms")], "no alert or SMS", evs)
    ctx.expect(len(ctx.outbox()) == out0, "outbox unchanged", ctx.outbox()[out0:])
    ui_assert(ctx, "status 'call ended'", lambda: pw_expect()(page.get_by_role("banner")).to_contain_text("call ended"))
    ui_assert(ctx, "Why panel: no alert, not a verdict",
              lambda: pw_expect()(card(page, "^Why this alert")).to_contain_text("No alert detected"))
    ctx.shot("ended-early")


@check("controls.reset-midway", "call-controls", ui=True)
def controls_reset(ctx: Context):
    ctx.api_reset()
    ctx.ensure_opted_in()
    consent0 = ctx.db_rows("SELECT phone_hash, state FROM consent ORDER BY phone_hash")
    counts0 = ctx.db_rows("SELECT keyword, template_id, count FROM reply_counts ORDER BY 1, 2")
    page = open_console(ctx)
    out0, mark = len(ctx.outbox()), ctx.tap.mark()
    ref, t0 = start_replay_ui(ctx, page, "Run bank", mark)
    ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "segment" and e["payload"]["seq"] == 2, mark, 15, "segment 2")
    click(ctx, page, "Reset")
    rst = ctx.wait_event(lambda e: e["type"] == "session" and e["payload"]["state"] == "reset", mark, 10, "reset event")
    ui_assert(ctx, "status 'reset'", lambda: pw_expect()(page.get_by_role("banner")).to_contain_text("reset"))
    ui_assert(ctx, "transcript cleared", lambda: pw_expect()(card(page, "^Live transcript")).to_contain_text("No call yet."))
    ctx.action("wait past where the alert would have fired (seq 4 ≈5.3 s) and the replay end (≈8 s)")
    time.sleep(max(0.0, 10 - (time.monotonic() - t0)))
    tail = ctx.tap.since(mark)
    late = [e for e in tail[tail.index(rst) + 1:] if e.get("session_ref") == ref]
    ctx.expect(not late, "no late events from the reset call (generation invariant)", late)
    ctx.expect(len(ctx.outbox()) == out0, "no SMS sent after reset", ctx.outbox()[out0:])
    ctx.expect(ctx.db_rows("SELECT phone_hash, state FROM consent ORDER BY phone_hash") == consent0, "reset preserved consent (SQLite)")
    ctx.expect(ctx.db_rows("SELECT keyword, template_id, count FROM reply_counts ORDER BY 1, 2") == counts0,
               "reset preserved reply counts (SQLite)")
    ctx.shot("after-reset")


def _run_clinic_mode(ctx: Context, page, mark_label: str) -> str:
    mark = ctx.tap.mark()
    click(ctx, page, "Run clinic")
    ev = ctx.wait_event(lambda e: e["type"] == "session" and e["payload"]["state"] == "running", mark, 10,
                        f"session running ({mark_label})")
    click(ctx, page, "Reset")
    ctx.wait_event(lambda e: e["type"] == "session" and e["payload"]["state"] == "reset", mark, 10, "reset")
    return ev["payload"]["sms_mode"]


@check("controls.sms-mode-toggle", "call-controls", ui=True)
def controls_mode(ctx: Context):
    ctx.api_reset()
    page = open_console(ctx)
    real, sim = (page.get_by_role("button", name=n, exact=True) for n in ("real", "simulated"))
    try:
        with page.expect_response(lambda r: r.url.endswith("/demo/sms-mode")) as resp:
            click(ctx, page, "real")
        ctx.expect(resp.value.status == 200, "POST /demo/sms-mode real -> 200", resp.value.status)
        ui_assert(ctx, "phone frame hidden in real mode", lambda: pw_expect()(card(page, "^Phone")).to_have_count(0))
        ui_assert(ctx, "'real' toggle highlighted", lambda: pw_expect()(real).to_have_class(re.compile(r"\bon\b")))
        # Safe: clinic never alerts, the run is reset at once, and the sandbox has no Twilio account.
        ctx.expect(_run_clinic_mode(ctx, page, "real") == "real", "backend starts the next call in real mode (SSE)")
    finally:
        with page.expect_response(lambda r: r.url.endswith("/demo/sms-mode")):
            click(ctx, page, "simulated")
    ui_assert(ctx, "phone frame back in simulated mode", lambda: pw_expect()(card(page, "^Phone")).to_be_visible())
    ui_assert(ctx, "'simulated' toggle highlighted", lambda: pw_expect()(sim).to_have_class(re.compile(r"\bon\b")))
    ctx.expect(_run_clinic_mode(ctx, page, "simulated") == "simulated", "backend back in simulated mode (SSE)")
    ctx.shot("simulated")


@check("controls.sms-mode-after-reload", "call-controls", ui=True)
def controls_mode_reload(ctx: Context):
    ctx.api_reset()
    page = open_console(ctx)
    try:
        with page.expect_response(lambda r: r.url.endswith("/demo/sms-mode")):
            click(ctx, page, "real")
        ctx.action("reload the console while the backend is in real mode")
        open_console(ctx)
        ctx.shot("reloaded-in-real-mode")
        ui_assert(ctx, "after reload the toggle still shows 'real' (operator sees the true SMS mode)",
                  lambda: pw_expect()(page.get_by_role("button", name="real", exact=True)).to_have_class(re.compile(r"\bon\b"), timeout=5_000))
    finally:
        ctx.api.post("/demo/sms-mode", json={"mode": "simulated"})


# --- twilio-webhooks --------------------------------------------------------------------------

def twilio_signature(token: str, url: str, params: dict) -> str:
    """Twilio's documented scheme, implemented independently of the app: base64(HMAC-SHA1(token,
    url + concat(sorted key+value)))."""
    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()


def post_twilio(ctx: Context, path: str, params: dict, sign: bool = True, bad: bool = False):
    headers = {}
    if sign:
        sig = twilio_signature(ctx.env["TWILIO_AUTH_TOKEN"], ctx.env["PUBLIC_BASE_URL"] + path, params)
        # corrupt deterministically: replacing with a fixed char is a no-op 1 time in 64
        headers["X-Twilio-Signature"] = (("B" if sig[0] == "A" else "A") + sig[1:]) if bad else sig
    return ctx.anon.post(path, data=params, headers=headers)


@check("webhooks.signature-required", "twilio-webhooks")
def webhooks_sig(ctx: Context):
    n, mark = ctx.reply_count("WRONG"), ctx.tap.mark()
    params = {"MessageSid": "SMverify" + uuid.uuid4().hex[:24], "Body": "WRONG", "From": ctx.env["DEMO_PHONE"]}
    for label, kw in (("unsigned", {"sign": False}), ("bad signature", {"bad": True})):
        r = post_twilio(ctx, "/sms/inbound", params, **kw)
        ctx.expect(r.status_code == 403, f"{label} POST /sms/inbound -> 403", r.status_code)
    r = post_twilio(ctx, "/sms/status", {"MessageSid": "SMx", "MessageStatus": "delivered"}, sign=False)
    ctx.expect(r.status_code == 403, "unsigned POST /sms/status -> 403", r.status_code)
    consent0 = ctx.consent_db()
    for label, sender in (("no sender", ""), ("unenrolled sender", "+10000000000")):
        r = post_twilio(ctx, "/sms/inbound", {"MessageSid": "SMverify" + uuid.uuid4().hex[:24], "Body": "STOP", "From": sender})
        ctx.expect(r.status_code == 200 and "<Response></Response>" in r.text,
                   f"signed STOP from {label} -> 200 empty TwiML (dropped, no retry)", [r.status_code, r.text])
    time.sleep(1)
    ctx.expect(not [e for e in ctx.tap.since(mark) if e["type"] in ("reply", "sms", "consent")],
               "no reply/sms/consent events emitted", ctx.tap.since(mark))
    ctx.expect(ctx.reply_count("WRONG") == n, "SQLite WRONG count unchanged", ctx.reply_count("WRONG"))
    ctx.expect(ctx.consent_db() == consent0, "demo phone consent unchanged by an unidentified STOP (SQLite)",
               ctx.consent_db())


@check("webhooks.signed-inbound-dedupe", "twilio-webhooks")
def webhooks_inbound(ctx: Context):
    n = ctx.reply_count("WRONG")
    params = {"MessageSid": "SMverify" + uuid.uuid4().hex[:24], "Body": "Wrong.", "From": ctx.env["DEMO_PHONE"]}
    mark = ctx.tap.mark()
    r = post_twilio(ctx, "/sms/inbound", params)
    ctx.expect(r.status_code == 200 and "<Response></Response>" in r.text and r.headers["content-type"].startswith("text/xml"),
               "signed inbound -> 200 empty TwiML", [r.status_code, r.headers.get("content-type"), r.text])
    rep = ctx.wait_event(lambda e: e["type"] == "reply", mark, 10, "reply event")["payload"]
    ctx.expect(rep["keyword"] == "WRONG", "'Wrong.' normalised to WRONG", rep)
    sms = ctx.wait_event(lambda e: e["type"] == "sms" and e["payload"]["template_id"] == "R-WRONG", mark, 5, "R-WRONG reply sms")
    ctx.expect(sms["payload"]["status"] == "delivered", "R-WRONG reply delivered by the simulated gateway", sms["payload"])
    delta = 1 if rep["counted"] else 0
    ctx.expect(ctx.reply_count("WRONG") == n + delta, f"SQLite WRONG count +{delta} (counted={rep['counted']})", ctx.reply_count("WRONG"))
    if "replay.bank-alert" in ctx.passed:
        ctx.expect(rep["counted"], "counted, since this run already produced an alert")
    mark2 = ctx.tap.mark()
    r = post_twilio(ctx, "/sms/inbound", params)
    ctx.expect(r.status_code == 200, "duplicate MessageSid still acknowledged 200", r.status_code)
    time.sleep(1.5)
    ctx.expect(not [e for e in ctx.tap.since(mark2) if e["type"] in ("reply", "sms")], "duplicate MessageSid ignored (no events)",
               ctx.tap.since(mark2))
    ctx.expect(ctx.reply_count("WRONG") == n + delta, "duplicate not counted again (SQLite)", ctx.reply_count("WRONG"))


@check("webhooks.status-callback", "twilio-webhooks")
def webhooks_status(ctx: Context):
    box = ctx.outbox()
    if not box:
        raise Blocked("no message in the simulated outbox to report status for")
    mid = box[-1]["message_id"]
    for status, mapped in (("delivered", "delivered"), ("undelivered", "failed")):
        mark = ctx.tap.mark()
        r = post_twilio(ctx, "/sms/status", {"MessageSid": mid, "MessageStatus": status})
        ctx.expect(r.status_code == 204, f"signed status {status} -> 204", r.status_code)
        ev = ctx.wait_event(lambda e: e["type"] == "sms" and e["payload"]["message_id"] == mid, mark, 5, f"sms {mapped} event")
        ctx.expect(ev["payload"]["status"] == mapped and ev["payload"]["template_id"] == box[-1]["template_id"],
                   f"status {status} relayed as {mapped} for {box[-1]['template_id']}", ev["payload"])
    mark = ctx.tap.mark()
    r = post_twilio(ctx, "/sms/status", {"MessageSid": "SMunknown" + uuid.uuid4().hex[:8], "MessageStatus": "delivered"})
    time.sleep(1)
    ctx.expect(r.status_code == 204 and not ctx.tap.since(mark), "unknown MessageSid -> 204, no event", [r.status_code, ctx.tap.since(mark)])


# --- live-call (Twilio voice webhook + Media Stream socket) -----------------------------------

def stream_url(ctx: Context) -> str:
    return "ws" + ctx.env["PUBLIC_BASE_URL"].removeprefix("http") + "/voice/stream"


def ws_connect(ctx: Context, signature: str | None):
    """Open /voice/stream the way Twilio does: the handshake carries x-twilio-signature over the
    stream URL with no params."""
    from websockets.sync.client import connect
    headers = {} if signature is None else {"x-twilio-signature": signature}
    return connect(ctx.inst["backend"].replace("http", "ws", 1) + "/voice/stream", additional_headers=headers)


def ulaw_frames(wav_path: Path) -> list[bytes]:
    """20 ms frames of 8 kHz mu-law, encoded by the stdlib (independent of the app's decoder)."""
    import audioop  # deprecated, still in 3.11
    import wave
    with wave.open(str(wav_path)) as w:
        assert (w.getframerate(), w.getsampwidth(), w.getnchannels()) == (8000, 2, 1), wav_path
        u = audioop.lin2ulaw(w.readframes(w.getnframes()), 2)
    return [u[i:i + 160] for i in range(0, len(u), 160)]


@check("voice.signature-required", "live-call")
def voice_sig(ctx: Context):
    from websockets.exceptions import InvalidStatus
    mark = ctx.tap.mark()
    params = {"CallSid": "CAverify" + uuid.uuid4().hex[:24], "From": "+10000000000"}
    for label, kw in (("unsigned", {"sign": False}), ("bad signature", {"bad": True})):
        r = post_twilio(ctx, "/voice/incoming", params, **kw)
        ctx.expect(r.status_code == 403, f"{label} POST /voice/incoming -> 403", r.status_code)
    good = twilio_signature(ctx.env["TWILIO_AUTH_TOKEN"], stream_url(ctx), {})
    for label, sig in (("unsigned", None), ("bad signature", ("B" if good[0] == "A" else "A") + good[1:])):
        try:
            ws_connect(ctx, sig).close()
            status = "accepted"
        except InvalidStatus as e:
            status = e.response.status_code
        ctx.expect(status == 403, f"{label} /voice/stream handshake -> 403", status)
    time.sleep(1)
    ctx.expect(not [e for e in ctx.tap.since(mark) if e["type"] == "session"], "no call session started", ctx.tap.since(mark))


@check("voice.incoming-twiml", "live-call")
def voice_twiml(ctx: Context):
    import xml.etree.ElementTree as ET
    r = post_twilio(ctx, "/voice/incoming", {"CallSid": "CAverify" + uuid.uuid4().hex[:24], "From": "+10000000000"})
    ctx.expect(r.status_code == 200 and r.headers["content-type"].startswith("text/xml"),
               "signed POST /voice/incoming -> 200 TwiML", [r.status_code, r.headers.get("content-type"), r.text])
    root = ET.fromstring(r.text)
    stream, dial = root.find("Start/Stream"), root.find("Dial")
    ctx.expect(stream is not None and stream.get("url") == stream_url(ctx) and stream.get("track") == "both_tracks",
               "TwiML starts a both-track stream to PUBLIC_BASE_URL/voice/stream", r.text)
    ctx.expect([c.tag for c in root] == ["Start", "Dial"] and dial.text == ctx.env["DEMO_PHONE"],
               "then dials DEMO_PHONE (stream first, so the bridge runs after it)", r.text)


@check("voice.bank-live-stream", "live-call", profile="asr", ui=True)
def voice_bank(ctx: Context):
    ctx.api_reset()
    ctx.ensure_opted_in()
    page = open_console(ctx)
    turns = json.loads((ctx.sandbox / "scenarios/demo/bank.json").read_text())["turns"]
    quiet = b"\xff" * 160
    ctx.action(f"stream the bank call's {len(turns)} turns over a signed /voice/stream in real time "
               "(caller -> inbound track, subscriber -> outbound, 0.8 s pause between turns)")
    mark, t = ctx.tap.mark(), 0
    sig = twilio_signature(ctx.env["TWILIO_AUTH_TOKEN"], stream_url(ctx), {})
    t0 = time.monotonic()
    with ws_connect(ctx, sig) as ws:
        ws.send(json.dumps({"event": "connected"}))
        ws.send(json.dumps({"event": "start", "start": {"tracks": ["inbound", "outbound"]}}))
        for turn in turns:
            track = "inbound" if turn["speaker"] == "caller" else "outbound"
            frames = ulaw_frames(ctx.sandbox / "audio/demo" / turn["audio"])
            for f in frames + [quiet] * 40:
                for tr, payload in ((track, f), ("outbound" if track == "inbound" else "inbound", quiet)):
                    ws.send(json.dumps({"event": "media", "media": {"track": tr, "timestamp": str(t),
                                                                   "payload": base64.b64encode(payload).decode()}}))
                t += 20
                time.sleep(max(0.0, t0 + t / 1000 - time.monotonic()))
        ws.send(json.dumps({"event": "stop"}))
    start = ctx.wait_event(lambda e: e["type"] == "session" and e["payload"]["state"] == "running", mark, 5, "session running")
    ref = start["session_ref"]
    ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "session" and e["payload"]["state"] == "finished",
                   mark, 60, "session finished")
    segs = [e["payload"] for e in events_for(ctx, mark, ref, "segment")]
    ctx.save_json("live-segments", segs)
    ctx.expect(segs and all(s["source"] == "asr" for s in segs), "every segment came from whisper (source asr)",
               [s["source"] for s in segs])
    ctx.expect({s["speaker"] for s in segs} == {"caller", "subscriber"},
               "both tracks transcribed and labelled (inbound caller, outbound subscriber)", [s["speaker"] for s in segs])
    ctx.expect([s["seq"] for s in segs] == list(range(1, len(segs) + 1)), "seq increases without gaps", [s["seq"] for s in segs])
    decs = events_for(ctx, mark, ref, "decision")
    ctx.expect([d["payload"]["template_id"] for d in decs] == ["ALERT-OTP-01"], "rules fire ALERT-OTP-01 on the live stream",
               [d["payload"] for d in decs])
    tr = card(page, "^Live transcript")
    ui_assert(ctx, "console shows the live transcript", lambda: pw_expect()(tr).to_contain_text(segs[0]["text"]))
    ui_assert(ctx, "transcript not labelled cached", lambda: pw_expect()(tr.get_by_text("cached transcript")).to_have_count(0))
    ctx.rec["timing"] = {"stream_wall_s": round(time.monotonic() - t0, 1)}
    ctx.shot("live-finished")


# --- enrollment-invite ------------------------------------------------------------------------

@check("invite.demo-and-spare", "enrollment-invite")
def invite(ctx: Context):
    for which, phone in (("spare", ctx.env["SPARE_PHONE"]), ("demo", ctx.env["DEMO_PHONE"])):
        mark = ctx.tap.mark()
        r = ctx.api.post("/sms/invite", json={"phone": which})
        ctx.expect(r.status_code == 200 and r.json().get("message_id"), f"POST /sms/invite {which} -> 200 with message id", r.text)
        mid = r.json()["message_id"]
        ev = ctx.wait_event(lambda e: e["type"] == "sms" and e["payload"]["message_id"] == mid, mark, 5, "ENROLL sms event")
        ctx.expect(ev["payload"]["template_id"] == "ENROLL" and ev["payload"]["status"] == "queued", "ENROLL queued", ev["payload"])
        last = ctx.outbox()[-1]
        ctx.expect(last["message_id"] == mid and last["text"] == ctx.templates["ENROLL"], "outbox has the ENROLL text", last)
        ctx.expect(ctx.consent_db(phone) == "invited", f"SQLite consent for the {which} phone's HMAC is invited",
                   ctx.consent_db(phone))
    r = ctx.api.post("/sms/invite", json={"phone": "other"})
    ctx.expect(r.status_code == 422, "an unknown phone name is rejected (no raw numbers cross the API)", r.status_code)
    ctx.action("restore demo consent: reply YES")
    ctx.api_reply("YES")
    ctx.expect(ctx.consent_db() == "active", "demo consent active again", ctx.consent_db())
    raw = (ctx.sandbox / "data/safesignal.db").read_bytes()
    digits = [ctx.env[k].lstrip("+") for k in ("DEMO_PHONE", "SPARE_PHONE")]
    ctx.expect(not any(d.encode() in raw or d.encode("utf-16-le") in raw for d in digits),
               "no raw phone number anywhere in the SQLite file", digits)


# --- asr-replay -------------------------------------------------------------------------------

@check("asr.bank-replay", "asr-replay", profile="asr", ui=True)
def asr_bank(ctx: Context):
    ctx.api_reset()
    ctx.ensure_opted_in()
    page = open_console(ctx)
    mark = ctx.tap.mark()
    ref, t0 = start_replay_ui(ctx, page, "Run bank", mark)
    ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "session" and e["payload"]["state"] == "finished",
                   mark, 120, "session finished")
    segs = [e["payload"] for e in events_for(ctx, mark, ref, "segment")]
    ctx.save_json("asr-segments", segs)
    log = (ctx.ev / "backend-asr.log").read_text(errors="replace")
    ctx.expect(segs and all(s["source"] == "asr" for s in segs), "every segment came from whisper (source asr), no cached fallback",
               [s["source"] for s in segs] or ("ASR unavailable" in log and log[log.index("ASR unavailable"):][:300]))
    dec = [e["payload"]["template_id"] for e in events_for(ctx, mark, ref, "decision")]
    ctx.expect(dec == ["ALERT-OTP-01"], "rules fire ALERT-OTP-01 on the transcribed audio", dec)
    tr = card(page, "^Live transcript")
    ui_assert(ctx, "transcript not labelled cached", lambda: pw_expect()(tr.get_by_text("cached transcript")).to_have_count(0))
    ui_assert(ctx, "transcript shows the first ASR segment", lambda: pw_expect()(tr).to_contain_text(segs[0]["text"]))
    ctx.rec["timing"] = {"replay_wall_s": round(time.monotonic() - t0, 1)}
    ctx.shot("asr-finished")


# --- live-mic ---------------------------------------------------------------------------------

def bank_turns(ctx: Context) -> list[tuple[str, Path]]:
    sc = json.loads((ctx.sandbox / "scenarios/demo/bank.json").read_text())
    return [(t["speaker"], ctx.sandbox / "audio/demo" / t["audio"]) for t in sc["turns"]]


def is_session(ref: str, state: str):
    return lambda e: e["session_ref"] == ref and e["type"] == "session" and e["payload"]["state"] == state


@check("live.api-turns", "live-mic", profile="asr")
def live_api_turns(ctx: Context):
    ctx.api_reset()
    ctx.ensure_opted_in()
    turns = bank_turns(ctx)
    out0, mark = len(ctx.outbox()), ctx.tap.mark()
    ctx.action("POST /live/start")
    r = ctx.api.post("/live/start", timeout=120)
    ctx.expect(r.status_code == 200, "POST /live/start -> 200", r.text)
    ref = r.json()["session_ref"]
    for speaker, wav in turns:
        ctx.action(f"POST /live/utterance speaker={speaker} audio={wav.name}")
        r = ctx.api.post("/live/utterance", data={"speaker": speaker},
                         files={"audio": (wav.name, wav.read_bytes(), "audio/wav")}, timeout=60)
        ctx.expect(r.status_code == 200 and r.json()["text"], f"{wav.name} transcribed", r.text)
    ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "sms" and e["payload"]["template_id"] == "ALERT-OTP-01",
                   mark, 10, "alert sms")
    ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "segment" and e["payload"]["seq"] == len(turns),
                   mark, 10, "segment for the last turn")
    evs = events_for(ctx, mark, ref)
    segs = [e["payload"] for e in evs if e["type"] == "segment"]
    ctx.save_json("live-segments", segs)
    ctx.expect([(s["seq"], s["speaker"], s["source"]) for s in segs] == [(i, sp, "asr") for i, (sp, _) in enumerate(turns, 1)],
               "one asr segment per turn, in order, with the speaker that was sent", segs)
    ctx.expect([e["payload"]["template_id"] for e in evs if e["type"] == "decision"] == ["ALERT-OTP-01"],
               "ALERT-OTP-01 fires mid-conversation", evs)
    ctx.expect(not any(is_session(ref, "finished")(e) for e in evs),
               "the alert did not end the conversation (the turn after it was still accepted)", evs)
    ctx.action("POST /demo/end-call")
    ctx.expect(ctx.api.post("/demo/end-call").status_code == 200, "POST /demo/end-call -> 200")
    ctx.wait_event(is_session(ref, "finished"), mark, 15, "session finished")
    order = [(e["type"], e["payload"].get("template_id") or e["payload"].get("state")) for e in events_for(ctx, mark, ref)
             if e["type"] in ("sms", "session")]
    ctx.save_json("event-order", order)
    ctx.expect(order == [("session", "running"), ("sms", "ALERT-OTP-01"), ("sms", "FU-OTP-01"), ("session", "finished")],
               "running -> alert -> follow-up only after End call -> finished", order)
    new = [m["template_id"] for m in ctx.outbox()[out0:]]
    ctx.expect(new == ["ALERT-OTP-01", "FU-OTP-01"], "outbox gained exactly the alert then the follow-up", new)


@check("live.mic-ui", "live-mic", profile="asr", ui=True)
def live_mic_ui(ctx: Context):
    ctx.api_reset()
    ctx.ensure_opted_in()
    page = open_console(ctx)
    mark = ctx.tap.mark()
    click(ctx, page, "Start live conversation")
    ref = ctx.wait_event(lambda e: e["type"] == "session" and e["payload"]["state"] == "running", mark, 120,
                         "session running")["session_ref"]
    you = page.get_by_role("button", name="You", exact=True)
    click(ctx, page, "Caller")
    ui_assert(ctx, "while Caller records, You is disabled", lambda: pw_expect()(you).to_be_disabled())
    ctx.action("talk for 5 s (Chromium's fake mic loops audio/demo/bank/t04.wav)")
    page.wait_for_timeout(5000)  # the length of the spoken turn, not a wait on the app
    click(ctx, page, "Caller - tap to stop")
    seg = ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "segment", mark, 60, "segment from the mic turn")["payload"]
    ctx.save_json("mic-segment", seg)
    ctx.expect(seg["speaker"] == "caller" and seg["source"] == "asr" and "code" in seg["text"].lower(),
               "the turn is transcribed as the caller asking for a code", seg)
    dec = ctx.wait_event(lambda e: e["session_ref"] == ref and e["type"] == "decision", mark, 15, "decision")["payload"]
    ctx.expect(dec["template_id"] == "ALERT-OTP-01", "ALERT-OTP-01 from the spoken turn", dec)
    tr, why = card(page, "^Live transcript"), card(page, "^Why this alert")
    ui_assert(ctx, "transcript card shows the 'Live mic' tag", lambda: pw_expect()(tr.get_by_text("Live mic", exact=True)).to_be_visible())
    ui_assert(ctx, "transcript shows the spoken turn", lambda: pw_expect()(tr).to_contain_text(seg["text"]))
    ui_assert(ctx, "Why panel headline 'Caller asked for a code'", lambda: pw_expect()(why).to_contain_text("Caller asked for a code"))
    ui_assert(ctx, "after the alert both speakers can still talk", lambda: pw_expect()(you).to_be_enabled())
    ctx.expect(not any(is_session(ref, "finished")(e) for e in events_for(ctx, mark, ref)), "the alert did not end the conversation")
    ctx.shot("alert-mid-call")
    click(ctx, page, "End call")
    ctx.wait_event(is_session(ref, "finished"), mark, 15, "session finished")
    ui_assert(ctx, "follow-up marker after End call",
              lambda: pw_expect()(tr.locator("p.marker")).to_have_text(["* Alert message sent to user", "* Follow-up message sent to user"]))
    ui_assert(ctx, "speaker buttons are gone once the call ended", lambda: pw_expect()(page.get_by_role("button", name="Caller", exact=True)).to_have_count(0))
    ctx.shot("ended")


# --- preflight (CLI, no server) ---------------------------------------------------------------

def _preflight(ctx: Context) -> dict:
    if "preflight" not in ctx.__dict__:
        env = sandbox_env(ctx.sandbox, "cli", None)
        env.pop("PUBLIC_BASE_URL", None)
        cmd = [sys.executable, "scripts/preflight_checks.py", "--no-sms"]
        ctx.action("$ " + " ".join(cmd[1:]) + "  (cwd sandbox, sandbox env, no .env)")
        p = subprocess.run(cmd, cwd=ctx.sandbox, env=env, capture_output=True, text=True, timeout=300)
        lines = {m.group(2): (m.group(1), m.group(3)) for m in re.finditer(r"^(PASS|FAIL|SKIP) (\S+) - (.*)$", p.stdout, re.M)}
        out = ctx.ev / "artifacts" / "preflight-stdout.txt"
        out.parent.mkdir(exist_ok=True)
        out.write_text(f"$ {' '.join(cmd)}\nexit {p.returncode}\n--- stdout\n{p.stdout}\n--- stderr\n{p.stderr[-4000:]}")
        ctx.preflight = {"rc": p.returncode, "lines": lines, "stdout": p.stdout, "env": env, "artifact": out}
    ctx.artifact(ctx.preflight["artifact"])
    return ctx.preflight


@check("preflight.offline-checks", "preflight", profile="cli")
def preflight_offline(ctx: Context):
    pf = _preflight(ctx)
    for name in ("app-offline", "cached-replay"):
        ctx.expect(pf["lines"].get(name, ("missing",))[0] == "PASS", f"preflight {name} PASS", pf["lines"].get(name))
    ctx.expect(pf["lines"].get("sms", ("",))[0] == "SKIP", "--no-sms skips the real text", pf["lines"].get("sms"))
    ctx.expect(pf["rc"] == 1 and "PREFLIGHT FAIL" in pf["stdout"],
               "overall FAIL without tunnel/Twilio/phones (no false PASS)", pf["rc"])
    leaked = [k for k in ("OPERATOR_PASSWORD", "SESSION_SECRET", "CONSENT_SALT", "TWILIO_AUTH_TOKEN") if pf["env"][k] in pf["stdout"]]
    ctx.expect(not leaked and pf["env"]["DEMO_PHONE"] not in pf["stdout"], "no secret or raw phone number printed", leaked)


@check("preflight.model", "preflight", profile="cli")
def preflight_model(ctx: Context):
    hf = Path(sandbox_env(ctx.sandbox, "cli", None)["HF_HOME"])
    if not (hf / "hub" / WHISPER_MODEL_DIR).is_dir():
        raise Blocked(f"whisper small.en not cached under {hf} (default {DEFAULT_HF_HOME})")
    pf = _preflight(ctx)
    ctx.expect(pf["lines"].get("model", ("missing",))[0] == "PASS", "preflight model PASS (loads offline)", pf["lines"].get("model"))


# --- negative control -------------------------------------------------------------------------

@check("control.invalid-assertion", "negative-control", control=True)
def negative_control(ctx: Context):
    """Deliberately false expectation against the real app. Must FAIL; a PASS means the
    harness can't fail and nothing it reports can be trusted."""
    ctx.api_reset()
    mark = ctx.tap.mark()
    ctx.expect(ctx.api.post("/demo/run/clinic").status_code == 202, "POST /demo/run/clinic -> 202")
    ev = ctx.wait_event(lambda e: e["type"] == "session" and e["payload"]["state"] == "running", mark, 10, "running")
    ctx.wait_event(lambda e: e["session_ref"] == ev["session_ref"] and e["type"] == "session"
                   and e["payload"]["state"] == "finished", mark, 40, "finished")
    dec = [e["payload"]["template_id"] for e in events_for(ctx, mark, ev["session_ref"], "decision")]
    ctx.expect(dec == ["ALERT-OTP-01"], "NEGATIVE CONTROL (deliberately false): the clinic call alerts", dec)
