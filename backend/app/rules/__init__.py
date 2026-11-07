"""Decision engine (§19.4). Pure: no SMS, DB, network or asyncio.

Both functions take every segment of the session so far and return the
session's cumulative results; the pipeline diffs against what it already
published or sent. Decision.basis holds the rule_ids of the RiskEvents behind it.

Skeleton stubs: return nothing. a-rules implements K/B (C stretch).
"""
from __future__ import annotations

from app.models import Arm, Decision, RiskEvent, Segment


def detect(segments: list[Segment], arm: Arm, policy_version: str) -> list[RiskEvent]:
    return []


def decide(segments: list[Segment], arm: Arm, policy_version: str) -> list[Decision]:
    return []
