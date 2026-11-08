"""Intent Evidence for arm C (PRD §4.3 contract, §19.4): zero-shot NLI on CPU.

`evidence(window)` scores the rolling transcript window (the last few turns plus
the triggering turn) against one hypothesis per category with
MoritzLaurer/deberta-v3-base-zeroshot-v2.0 and returns one label plus a
confidence_class. In-process only; the window never leaves the machine.

`classify(window)` is what app.rules calls: the alert Category for an action label
(always medium or high confidence), else None (abstain). The rules only accept it
when the lexicon already saw that category, so the model never acts alone. The
authority/urgency label has no alert of its own and classifies as None.

Off unless env INTENT_MODEL=on and the `[intent]` extra is installed
(`uv sync --extra intent`). When off, classify abstains and arm C equals arm B.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import threading
from functools import lru_cache
from typing import Literal, NamedTuple

from app.models import Category, ConfidenceClass, Segment

MODEL = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"
Label = Literal["credential_or_code_request", "payment_or_transfer_request", "remote_access_request",
                "authority_or_relationship_claim_with_urgency", "none", "abstain"]
# One hypothesis per category.
HYPOTHESES = {
    "credential_or_code_request": "The caller asks the listener to share a verification code, PIN or password.",
    "payment_or_transfer_request": "The caller is asking for money.",
    "remote_access_request": "The caller asks the listener to install software or let them control a device.",
    "authority_or_relationship_claim_with_urgency":
        "The caller claims to be a relative or an official and says it is urgent.",
}
CATEGORY: dict[str, Category] = {"credential_or_code_request": "otp", "payment_or_transfer_request": "payment",
                                 "remote_access_request": "remote"}
# Entailment-probability bands (uncalibrated). A label needs MEDIUM (action labels
# are tried before the authority claim); "none" needs every score at or below
# NONE_MAX; anything in between abstains.
HIGH, MEDIUM, NONE_MAX = 0.9, 0.7, 0.3

log = logging.getLogger(__name__)
_model = None
_failed = False
_lock = threading.Lock()


class Evidence(NamedTuple):
    label: Label
    confidence_class: ConfidenceClass


def enabled() -> bool:
    """INTENT_MODEL=on and the [intent] extra is installed."""
    return (os.environ.get("INTENT_MODEL", "").strip().lower() == "on"
            and all(importlib.util.find_spec(m) for m in ("torch", "transformers")))


def load_model():
    """Load (once) and return (tokenizer, model). Raises if it can't be loaded."""
    global _model
    with _lock:
        if _model is None:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            # transformers 5 keeps the checkpoint dtype (fp16 here), which is ~6x slower on CPU.
            model = AutoModelForSequenceClassification.from_pretrained(MODEL, dtype=torch.float32).eval()
            _model = AutoTokenizer.from_pretrained(MODEL), model
    return _model


def preload() -> None:
    """Load and warm the model at startup when enabled. Never raises."""
    if not enabled():
        return
    try:
        _scores("Caller: Hello, how are you today?")
    except Exception:
        log.exception("Intent model failed to load; arm C will equal arm B")


def _scores(premise: str) -> dict[str, float]:
    import torch
    tokenizer, model = load_model()
    enc = tokenizer([premise] * len(HYPOTHESES), list(HYPOTHESES.values()),
                    return_tensors="pt", padding=True, truncation=True)
    with torch.inference_mode():
        probs = model(**enc).logits.softmax(-1)[:, model.config.label2id["entailment"]]
    return dict(zip(HYPOTHESES, probs.tolist()))


@lru_cache(maxsize=4096)
def _evidence(premise: str) -> Evidence:
    scores = _scores(premise)
    for label, p in sorted(scores.items(), key=lambda kv: (kv[0] not in CATEGORY, -kv[1])):
        if p >= MEDIUM:
            return Evidence(label, "high" if p >= HIGH else "medium")
    top = max(scores.values())
    if top <= NONE_MAX:
        return Evidence("none", "high" if top <= 1 - HIGH else "medium")
    return Evidence("abstain", "low")


def evidence(window: list[Segment]) -> Evidence:
    """Intent Evidence for a window (cached by text). Raises if the model can't be loaded."""
    return _evidence("\n".join(f"{s.speaker.capitalize()}: {s.text}" for s in window))


def classify(window: list[Segment]) -> Category | None:
    """The window's alert category, or None to abstain (also when the model is off or broken)."""
    global _failed
    if _failed or not enabled():
        return None
    try:
        return CATEGORY.get(evidence(window).label)
    except Exception:
        _failed = True
        log.exception("Intent model unavailable; arm C will equal arm B")
        return None
