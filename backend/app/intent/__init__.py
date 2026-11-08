"""Intent evidence for arm C (PRD §4.3, §19.4) from TypeSafe's Jev (System One API).

Jev makes atomic judgments; code decides. For each caller turn we send one request
whose state is the current caller turn plus the few turns before it (speaker-labelled).
It bundles, answered in parallel:
- request Nouls, several per alert category (one per way of handing over a code, money or
  device access), combined with OR (the max);
- guard Nouls for the known false-positive patterns (a warning, a request someone else
  made, something already done, paying a payee the listener chose, doing it yourself);
- a pressure Noul (urgency or threats) that lets a likely request through raised guards.
`judge` maps those answers to a decision per category: evidence ("confirm" when the
lexicon saw the category in the window, else model-only "solo"), a "veto" of the rules'
request on that turn, or nothing. All question wording and thresholds live in this module.

Only on when env INTENT_MODEL=on and TYPESAFE_API_KEY is set. A failed call is an
error, never a "no": it is logged and arm C falls back to arm B for that turn.
The window leaves the machine only when arm C is on; it is never stored.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Literal

import httpx

from app.models import Category, Segment

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.14.0"  # pinned: thresholds below were tuned on this version
TIMEOUT_S = 1.5  # per caller turn, retry included (PRD 19.7 latency budget)
CONNECT_S = 0.5  # a TLS handshake slower than this is abandoned and retried once ...
RETRY_MIN_S = 0.3  # ... if at least this much of the turn's budget is left
KEEPALIVE_S = 120  # keep the connection warm between turns of a call
_RETRYABLE = (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ReadError,
              httpx.WriteError)
CONTEXT_TURNS = 3  # earlier turns sent with the caller turn

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
CATEGORIES: tuple[Category, ...] = ("otp", "payment", "remote")
REQUESTS: dict[Category, tuple[str, ...]] = {
    "otp": ("otp", "otp_code", "otp_secret"),
    "payment": ("payment", "pay_cards", "pay_send", "pay_details"),
    "remote": ("remote", "rem_install", "rem_control"),
}
# Each guard only where it separates the classes on training data: "known_payee" for money,
# "self_service" for device access only (for codes and money it also fires on real scams:
# "go buy the cards yourself").
_COMMON_GUARDS = ("warning", "reported", "done")
GUARDS: dict[Category, tuple[str, ...]] = {
    "otp": _COMMON_GUARDS,
    "payment": _COMMON_GUARDS + ("known_payee",),
    "remote": _COMMON_GUARDS + ("self_service",),
}

# Thresholds, tuned on dev + t1/t2 (Claude-written calls) and validated on H2 (GPT-written),
# and the reverse; both directions chose this region (report on issue #67).
CERTAIN = 0.97  # a request this sure is evidence whatever the guards say
LIKELY = 0.7  # a request this sure is evidence when no guard is raised
GUARD_MAX = 0.3  # a guard at or above this is raised
PRESSED_REQUEST = 0.85  # ... but a request this sure
PRESSURE = 0.7  # ... from a caller pressing this hard overrules the guards

Judgment = Literal["confirm", "solo", "veto"]

log = logging.getLogger(__name__)
_cache: dict[str, dict[str, float] | None] = {}
_lock = threading.Lock()
failures = 0  # failed calls since start (each fell back to arm B), for eval provenance
_http: httpx.Client | None = None


def enabled() -> bool:
    """INTENT_MODEL=on and TYPESAFE_API_KEY is set."""
    return (os.environ.get("INTENT_MODEL", "").strip().lower() == "on"
            and bool(os.environ.get("TYPESAFE_API_KEY", "").strip()))


def preload() -> None:
    """Nothing to load for a hosted model; log whether arm C can call it."""
    if os.environ.get("INTENT_MODEL", "").strip().lower() == "on" and not enabled():
        log.warning("INTENT_MODEL=on but TYPESAFE_API_KEY is not set; arm C will equal arm B")
    elif enabled():
        log.info("arm C on: each caller turn and the %d prior turns are sent to %s", CONTEXT_TURNS, URL)


def state(window: list[Segment]) -> dict:
    """Request state: the last turn (a caller turn) and the turns just before it."""
    *earlier, current = window
    return {
        "earlier_turns": [{"speaker": "caller" if s.speaker == "caller" else "listener", "text": s.text}
                          for s in earlier[-CONTEXT_TURNS:]],
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
    """POST one System One request within TIMEOUT_S in total. A connection that fails to open, or a
    kept-alive one the server already closed, is retried once if time is left (the request is
    idempotent). Raises on any other transport or HTTP error."""
    deadline = time.monotonic() + TIMEOUT_S
    headers = {"Authorization": f"Bearer {os.environ['TYPESAFE_API_KEY'].strip()}"}
    try:
        r = _client().post(URL, json=body, headers=headers, timeout=httpx.Timeout(TIMEOUT_S, connect=CONNECT_S))
    except _RETRYABLE as e:
        left = deadline - time.monotonic()
        if left < RETRY_MIN_S:
            raise
        log.warning("TypeSafe connection failed (%s); retrying once", type(e).__name__)
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
    log.debug("typesafe request: %d earlier turns, %d questions", len(body["state"]["earlier_turns"]),
              len(body["questions"]))  # never the call text
    try:
        resp = _post(body)
        result = {q: float(resp["answers"][q]["noul"]) for q in QUESTIONS}
    except Exception as e:  # an error, never a "no": arm C falls back to arm B for this turn
        global failures
        with _lock:
            failures += 1
        log.error("TypeSafe call failed (%s: %s); arm C falls back to arm B for this turn", type(e).__name__, e)
        result = None
    with _lock:
        _cache[key] = result
    return result


def judge(ans: dict[str, float], category: Category, lexicon_seen: bool,
          rule_fired: bool = False) -> Judgment | None:
    """The decision table for one category on one caller turn.

    request = max of the category's request Nouls; guarded = any of its guards >= GUARD_MAX;
    pressed = request >= PRESSED_REQUEST and pressure >= PRESSURE (overrules raised guards).
    - request >= CERTAIN, or request >= LIKELY and (not guarded or pressed): evidence. It
      confirms the category when the lexicon saw it in the window, else it is model-only (solo).
    - the rules fired on this turn (rule_fired), but guarded, not pressed and request < CERTAIN:
      "veto" (a warning, a report or a done deal that the rules read as a request).
    - anything else: no judgment (a rules request stands; no model evidence).
    """
    request = max(ans[q] for q in REQUESTS[category])
    guarded = max(ans[g] for g in GUARDS[category]) >= GUARD_MAX
    pressed = request >= PRESSED_REQUEST and ans["pressure"] >= PRESSURE
    if rule_fired:
        return "veto" if guarded and not pressed and request < CERTAIN else None
    if request >= CERTAIN or (request >= LIKELY and (pressed or not guarded)):
        return "confirm" if lexicon_seen else "solo"
    return None


def clear_cache() -> None:
    """Drop cached windows (call text) when a session ends (PRD §12 transient content)."""
    with _lock:
        _cache.clear()
