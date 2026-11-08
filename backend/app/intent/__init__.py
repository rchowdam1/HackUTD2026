"""Intent evidence for arm C (PRD §4.3, §19.4) from Perplexity's Decider V1.2, a decision model
called through OpenRouter's Decisions API (OpenRouter forwards each request to a host of the model).

The model makes atomic judgments; code decides. For each caller turn we send one request
whose state is the current caller turn plus the few turns before it (speaker-labelled).
It bundles, answered in parallel:
- request Nouls, several per alert category (one per way of handing over a code, money or
  device access), combined with OR (the max) within a request group;
- guard Nouls for the known false-positive patterns (a warning, a request someone else
  made, something already done, paying a payee the listener chose, doing it yourself),
  each applied only to the request groups where it separates scams from benign calls;
- a pressure Noul (urgency or threats) that lets a sure request through situational guards.
`judge` maps those answers to a decision per category: evidence ("confirm" when the
lexicon saw the category in the window, else model-only "solo"), a "veto" of the rules'
request on that turn, or nothing. All question wording and thresholds live in this module.

Only on when env INTENT_MODEL=on and OPENROUTER_API_KEY is set. A failed call is an
error, never a "no": it is logged and arm C falls back to arm B for that turn.
The window leaves the machine only when arm C is on; it is never stored.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Literal, get_args

import httpx

from app.models import Category, Segment

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "perplexity/pplx-decider-v1.2-20261016"  # pinned snapshot: thresholds below depend on it
TIMEOUT_S = 1.5  # per caller turn, retry included (PRD 19.7 latency budget)
CONNECT_S = 0.5  # a TLS handshake slower than this is abandoned and retried once ...
RETRY_MIN_S = 0.3  # ... if at least this much of the turn's budget is left
KEEPALIVE_S = 120  # keep the connection warm between turns of a call
_RETRYABLE = (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ReadError,
              httpx.WriteError)

# Who is who, in plain words; every question refers to the state by these paths.
_WHO = "The caller phoned the listener. "
_CONTEXT = " `earlier_turns` shows what was said just before."


def _noul(question: str, true: str | None = None, false: str | None = None) -> dict:
    q: dict = {"type": "noul", "instructions": _WHO + question + _CONTEXT}
    if true or false:
        q["criteria"] = {"true": true, "false": false}
    return q


QUESTIONS: dict[str, dict] = {
    # --- Requests: is the caller asking for it? Several per category, combined with OR. ---
    # A code or secret.
    "otp": {
        "type": "noul",
        "instructions": _WHO + "In `caller_turn`, does the caller ask the listener to tell, read out or send "
                               "them a code, PIN, password or other secret number? `earlier_turns` shows what "
                               "was said just before.",
        "criteria": {
            "true": "The caller wants to hear or receive the secret, e.g. a verification code that was just "
                    "texted, the numbers on the screen, or what the text message says.",
            "false": "The caller only mentions a code, or wants it typed into an app or website by the "
                     "listener without the caller learning it.",
        },
    },
    "otp_code": _noul(
        "In `caller_turn`, does the caller ask the listener to read out, say, send or key in for them a code or "
        "number that the listener received by text, email, app or letter?",
        "The caller wants to learn the code: the listener is to read it, say it, text it or pass it on to the "
        "caller or to someone the caller names.",
        "The caller only mentions a code, or tells the listener to type it into their own app or website."),
    "otp_secret": _noul(
        "In `caller_turn`, does the caller ask the listener to tell them a password, PIN or the answer to a "
        "security question?",
        "The caller wants to learn the secret, including by having the listener key it in on the phone keypad "
        "during the call.",
        "The caller only mentions a password or PIN, or tells the listener to change it on their own."),
    "otp_hear": _noul(
        "In `caller_turn`, does the caller want the listener to read out, say or repeat to them a number or code "
        "from a text, email, letter, card or screen?"),
    # Money.
    "payment": {
        "type": "noul",
        "instructions": _WHO + "In `caller_turn`, does the caller ask the listener to pay, send or transfer "
                               "money? `earlier_turns` shows what was said just before.",
        "criteria": {
            "true": "The caller wants money from the listener now, in any form: a payment, card details, gift "
                    "cards or vouchers, cash handed to a courier, crypto, a wire or a payment app.",
            "false": "The caller says nothing is owed, a bill is already paid, or the caller is sending money "
                     "to the listener.",
        },
    },
    "pay_cards": _noul(
        "In `caller_turn`, does the caller ask the listener to buy gift cards, prepaid cards or vouchers, or to "
        "give the caller the numbers on such cards?"),
    "pay_send": _noul(
        "In `caller_turn`, does the caller ask the listener to send or move money, for example by bank transfer, "
        "wire, payment app, crypto, top-up, or cash that is mailed or handed to a courier?",
        "The caller wants money to leave the listener's control now or soon.",
        "The caller says the money was already sent, or the caller is the one sending money to the listener."),
    "pay_details": _noul(
        "In `caller_turn`, does the caller ask the listener for card or bank account details, or to pay a fee, "
        "fine or bill over the phone?"),
    # Device access.
    "remote": {
        "type": "noul",
        "instructions": _WHO + "In `caller_turn`, does the caller ask the listener to install software, open "
                               "a website or link, or let the caller access or control their device? "
                               "`earlier_turns` shows what was said just before.",
        "criteria": {
            "true": "The caller wants the listener to take a step on their computer or phone that the caller "
                    "directs, e.g. download an app, go to a site, click allow, or share the screen.",
            "false": "The caller only talks about a device or an app, or says no access or install is needed.",
        },
    },
    "rem_install": _noul(
        "In `caller_turn`, does the caller ask the listener to download, install, launch or run an app, program "
        "or tool?"),
    "rem_control": _noul(
        "In `caller_turn`, does the caller ask the listener to share their screen, or to let the caller or "
        "their staff see, connect to or control the listener's device?"),
    # Who ends up inside the device: the caller's side (a scam) or nobody (do-it-yourself help).
    "rem_access": _noul(
        "In `caller_turn`, does the caller ask for a step that would let the caller, or people working with the "
        "caller, see, connect to or control the listener's computer, phone or online accounts?",
        "The caller's side would get into the listener's device or account, e.g. through a tool the listener "
        "installs, a connection or session the listener accepts or joins, the listener sharing their screen, or "
        "remote control turned on.",
        "The listener makes the change or installs something on their own, the caller shows the listener the "
        "caller's own screen, or the caller is retelling what someone else asked for."),
    # --- Guards: the usual false-positive patterns, one judgment each. ---
    "warning": {
        "type": "noul",
        "instructions": _WHO + "In `caller_turn`, is the caller warning the listener about scams or saying "
                               "what they or their organisation will never ask for?",
    },
    "reported": _noul(
        "In `caller_turn`, is the caller only telling the listener about something that someone else asked for "
        "or did, without asking the listener to do anything now?"),
    "done": _noul(
        "In `caller_turn`, is the caller saying that the payment, code or fix is already taken care of, so "
        "nothing is needed from the listener?"),
    "known_payee": _noul(
        "In `caller_turn`, is the caller telling the listener to pay a business or person the listener chose "
        "themselves, for goods or a service the listener asked for, in the usual way?",
        "The listener pays for work or goods they ordered, or a bill they expected, through their normal way "
        "of paying.",
        "The caller wants payment sent to an account, card, person or method that the caller names, or for a "
        "debt, fee or problem the listener did not know about."),
    "self_service": {
        "type": "noul",
        "instructions": _WHO + "In `caller_turn`, does the caller tell the listener to do it themselves, "
                               "without giving the code, money or access to the caller?",
    },
    # --- Context: scam pressure lets a likely request through raised guards. ---
    "pressure": _noul(
        "Is the caller pushing the listener to act right away, or warning of a bad outcome such as arrest, a "
        "frozen account, lost money or harm to someone if they don't?"),
}
CATEGORIES: tuple[Category, ...] = get_args(Category)
# Per category, request groups: (request Nouls combined with OR, the guards that block them).
# Each guard only where it separates the classes on training data (all three writer sets):
# - "done" never separated codes (it fires on "read it and you're all set"), so codes don't use it;
# - "known_payee" is for money only;
# - "self_service" blocks only the broad device requests (install, open), and only when near-sure:
#   real scams also say "install it yourself", but they still want the caller's side let in, which
#   rem_control / rem_access ask directly.
_SAY = ("warning", "reported")
GROUPS: dict[Category, tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]] = {
    "otp": ((("otp", "otp_code", "otp_secret", "otp_hear"), _SAY),),
    "payment": ((("payment", "pay_cards", "pay_send", "pay_details"), _SAY + ("done", "known_payee")),),
    "remote": ((("rem_control", "rem_access"), _SAY),
               (("remote", "rem_install"), _SAY + ("done", "self_service"))),
}
REQUESTS: dict[Category, tuple[str, ...]] = {c: tuple(q for qs, _ in GROUPS[c] for q in qs) for c in CATEGORIES}
GUARDS: dict[Category, tuple[str, ...]] = {c: tuple(dict.fromkeys(g for _, gs in GROUPS[c] for g in gs))
                                           for c in CATEGORIES}
# Near-certain evidence whatever the situational guards say. For device access only the direct
# "let the caller in" Nouls: a sure "install it" is just as sure when the listener does it alone.
SURE: dict[Category, tuple[str, ...]] = {"otp": REQUESTS["otp"], "payment": REQUESTS["payment"],
                                         "remote": ("rem_control", "rem_access")}
PRESSABLE = ("reported", "done", "known_payee")  # situational guards that scam pressure overrules

# Thresholds, chosen on TypeSafe Jev 1.14 (the previous model) by leave-one-writer-set-out validation
# (Claude / GPT+Cursor / mixed sets; report on issue #67). Not re-tuned for Decider V1.2.
CERTAIN = 0.95  # a SURE request this sure is evidence unless the caller is warning about it
LIKELY = 0.7  # a request this sure is evidence when none of its group's guards is raised
GUARD_MAX = 0.4  # a guard at or above this is raised ...
GUARD_BAR = {"reported": 0.5, "self_service": 0.8}  # ... except these, which also fire on scams
WARNED = 0.7  # a warning this sure blocks even a near-certain request and vetoes a rules hit
PRESSED_REQUEST = 0.85  # a request this sure
PRESSURE = 0.7  # ... from a caller pressing this hard overrules the PRESSABLE guards
NO_REQUEST = 0.3  # a rules hit the model scores below this as a request ...
DIY = 0.8  # ... is vetoed when the model is this sure the caller says "do it yourself"

Judgment = Literal["confirm", "solo", "veto"]

log = logging.getLogger(__name__)
_cache: dict[str, dict[str, float] | None] = {}
_lock = threading.Lock()
failures = 0  # failed calls since start (each fell back to arm B), for eval provenance
_http: httpx.Client | None = None


def enabled() -> bool:
    """INTENT_MODEL=on and OPENROUTER_API_KEY is set."""
    return _flag_on() and bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


def _flag_on() -> bool:
    return os.environ.get("INTENT_MODEL", "").strip().lower() == "on"


def preload() -> None:
    """Nothing to load for a hosted model; log whether arm C can call it."""
    if enabled():
        log.info("arm C on: each caller turn and the turns before it (rules.yaml context_turns) are sent to %s "
                 "(OpenRouter, model %s)", URL, MODEL)
    elif _flag_on():
        log.warning("INTENT_MODEL=on but OPENROUTER_API_KEY is not set; arm C will equal arm B")


def state(window: list[Segment]) -> dict:
    """Request state: the last turn (a caller turn) and the turns before it in the window."""
    *earlier, current = window
    return {
        "earlier_turns": [{"speaker": "caller" if s.speaker == "caller" else "listener", "text": s.text}
                          for s in earlier],
        "caller_turn": current.text,
    }


def payload(window: list[Segment]) -> dict:
    return {"model": MODEL, "state": state(window), "questions": QUESTIONS}


def _client() -> httpx.Client:
    """One client per process, so turns reuse a warm TLS connection (keep-alive)."""
    global _http
    with _lock:
        if _http is None:
            _http = httpx.Client(limits=httpx.Limits(keepalive_expiry=KEEPALIVE_S))
        return _http


def _post(body: dict) -> dict:
    """POST one Decisions request within TIMEOUT_S in total. A connection that fails to open, or a
    kept-alive one the server already closed, is retried once if time is left (the request is
    idempotent). Raises on any other transport or HTTP error."""
    deadline = time.monotonic() + TIMEOUT_S
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY'].strip()}"}
    try:
        r = _client().post(URL, json=body, headers=headers, timeout=httpx.Timeout(TIMEOUT_S, connect=CONNECT_S))
    except _RETRYABLE as e:
        left = deadline - time.monotonic()
        if left < RETRY_MIN_S:
            raise
        log.warning("OpenRouter connection failed (%s); retrying once", type(e).__name__)
        r = _client().post(URL, json=body, headers=headers, timeout=left)
    r.raise_for_status()
    return r.json()


def answers(window: list[Segment]) -> dict[str, float] | None:
    """Noul per question id for a window ending in a caller turn, or None if the model is off
    or the call failed (the failure is logged as an error). Cached per window text."""
    if not window or not enabled():
        return None
    body = payload(window)
    key = json.dumps(body["state"], sort_keys=True)
    with _lock:
        if key in _cache:
            return _cache[key]
    log.debug("intent request: %d earlier turns, %d questions", len(body["state"]["earlier_turns"]),
              len(body["questions"]))  # never the call text
    try:
        resp = _post(body)
        result = {q: float(resp["answers"][q]["noul"]) for q in QUESTIONS}
    except Exception as e:  # an error, never a "no": arm C falls back to arm B for this turn
        global failures
        with _lock:
            failures += 1
        log.error("Intent model call failed (%s: %s); arm C falls back to arm B for this turn", type(e).__name__, e)
        result = None
    with _lock:
        _cache[key] = result
    return result


def _bar(guard: str) -> float:
    return GUARD_BAR.get(guard, GUARD_MAX)


def request_score(ans: dict[str, float], category: Category) -> float:
    """The model's probability that the caller asked for something in this category (any way of asking)."""
    return max(ans[q] for q in REQUESTS[category])


def _evidence(ans: dict[str, float], category: Category) -> bool:
    """Does the model, on its own, find a request in this category on this turn?"""
    if ans["warning"] >= WARNED:
        return False
    if max(ans[q] for q in SURE[category]) >= CERTAIN:
        return True
    pressured = ans["pressure"] >= PRESSURE
    for requests, guards in GROUPS[category]:
        request = max(ans[q] for q in requests)
        if request < LIKELY:
            continue
        raised = [g for g in guards if ans[g] >= _bar(g)]
        if not raised or (request >= PRESSED_REQUEST and pressured and set(raised) <= set(PRESSABLE)):
            return True
    return False


def judge(ans: dict[str, float], category: Category, lexicon_seen: bool,
          rule_fired: bool = False) -> Judgment | None:
    """The decision table for one category on one caller turn.

    Evidence (`_evidence`), unless the caller is warning (warning >= WARNED):
    - a SURE request Noul >= CERTAIN; or
    - in some request group, request (max of its Nouls) >= LIKELY and none of its guards raised
      (guard >= its bar), or request >= PRESSED_REQUEST under pressure >= PRESSURE with only
      PRESSABLE guards raised.
    Evidence confirms the category when the lexicon saw it in the window, else it is model-only (solo).
    The rules fired on this turn (rule_fired) and the model finds no evidence: "veto" when a warning, a guard
    of the category is raised, or the model scores the request < NO_REQUEST and do-it-yourself >= DIY.
    Anything else: no judgment (a rules request stands; no model evidence).
    """
    evidence = _evidence(ans, category)
    if not rule_fired:
        return ("confirm" if lexicon_seen else "solo") if evidence else None
    if evidence:
        return None
    guarded = any(ans[g] >= _bar(g) for g in GUARDS[category])
    no_request = request_score(ans, category) < NO_REQUEST and ans["self_service"] >= DIY
    return "veto" if guarded or no_request else None


def clear_cache() -> None:
    """Drop cached windows (call text) when a session ends (PRD §12 transient content)."""
    with _lock:
        _cache.clear()
