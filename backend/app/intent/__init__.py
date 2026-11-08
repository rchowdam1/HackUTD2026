"""Intent evidence for arm C (PRD §4.3, §19.4) from TypeSafe's Jev (System One API).

Jev makes atomic judgments; code decides. For each caller turn we send one request
whose state is the current caller turn plus the few turns before it (speaker-labelled)
and ask one Noul per alert category plus Nouls for the known false-positive patterns.
`judge` combines those answers with thresholds into "confirm" (the lexicon saw the
category, the model agrees), "solo" (the model alone, stricter bar) or nothing.
All question wording and thresholds live in this module.

Only on when env INTENT_MODEL=on and TYPESAFE_API_KEY is set. A failed call is an
error, never a "no": it is logged and arm C falls back to arm B for that turn.
The window leaves the machine only when arm C is on; it is never stored.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Literal

import httpx

from app.models import Category, Segment

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.14.0"  # pinned: thresholds below were tuned on this version
TIMEOUT_S = 1.5  # per caller turn (PRD 19.7 latency budget)
CONTEXT_TURNS = 3  # earlier turns sent with the caller turn

# Who is who, in plain words; every question refers to the state by these paths.
_WHO = "The caller phoned the listener. "
QUESTIONS: dict[str, dict] = {
    # One request Noul per alert category.
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
    # False-positive patterns (one judgment each).
    "warning": {
        "type": "noul",
        "instructions": _WHO + "In `caller_turn`, is the caller warning the listener about scams or saying "
                               "what they or their organisation will never ask for?",
    },
    "reported": {
        "type": "noul",
        "instructions": _WHO + "In `caller_turn`, is the caller describing a request that someone else made, "
                               "rather than asking the listener for something themselves?",
    },
    "self_service": {
        "type": "noul",
        "instructions": _WHO + "In `caller_turn`, does the caller tell the listener to do it themselves, "
                               "without giving the code, money or access to the caller?",
    },
}
CATEGORIES: tuple[Category, ...] = ("otp", "payment", "remote")
GUARDS = ("warning", "reported", "self_service")

# Noul thresholds (skill defaults 0.7 / 0.3, then tuned on training data t1).
CONFIRM = 0.7  # the category's request Noul, when the lexicon saw the category
SOLO = 0.9  # the category's request Noul, with no lexicon support
GUARD_MAX = 0.3  # every guard Noul must be below this for a solo detection
GUARD_CONFIRM_MAX = 0.7  # ... and below this for a confirmation

Judgment = Literal["confirm", "solo"]

log = logging.getLogger(__name__)
_cache: dict[str, dict[str, float] | None] = {}
_lock = threading.Lock()


def enabled() -> bool:
    """INTENT_MODEL=on and TYPESAFE_API_KEY is set."""
    return (os.environ.get("INTENT_MODEL", "").strip().lower() == "on"
            and bool(os.environ.get("TYPESAFE_API_KEY", "").strip()))


def preload() -> None:
    """Nothing to load for a hosted model; log whether arm C can call it."""
    if os.environ.get("INTENT_MODEL", "").strip().lower() == "on" and not enabled():
        log.warning("INTENT_MODEL=on but TYPESAFE_API_KEY is not set; arm C will equal arm B")


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


def _post(body: dict) -> dict:
    """POST one System One request. Raises on any transport or HTTP error."""
    r = httpx.post(URL, json=body, timeout=TIMEOUT_S,
                   headers={"Authorization": f"Bearer {os.environ['TYPESAFE_API_KEY'].strip()}"})
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
    if log.isEnabledFor(logging.DEBUG):
        log.debug("typesafe request %s", json.dumps(body))
    try:
        resp = _post(body)
        result = {q: float(resp["answers"][q]["noul"]) for q in QUESTIONS}
    except Exception as e:  # an error, never a "no": arm C falls back to arm B for this turn
        log.error("TypeSafe call failed (%s: %s); arm C falls back to arm B for this turn", type(e).__name__, e)
        result = None
    with _lock:
        _cache[key] = result
    return result


def judge(ans: dict[str, float], category: Category, lexicon_seen: bool) -> Judgment | None:
    """The decision table. A confirmation needs the lexicon to have seen the category."""
    p = ans[category]
    guard = max(ans[g] for g in GUARDS)
    if p >= SOLO and guard < GUARD_MAX:
        return "confirm" if lexicon_seen else "solo"
    if lexicon_seen and p >= CONFIRM and guard < GUARD_CONFIRM_MAX:
        return "confirm"
    return None


def clear_cache() -> None:
    """Drop cached windows (call text) when a session ends (PRD §12 transient content)."""
    with _lock:
        _cache.clear()
