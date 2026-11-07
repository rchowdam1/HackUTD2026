"""Decision engine (§19.4). Pure: no SMS, DB, network or asyncio.

Skeleton stub: returns no decisions. a-rules implements K/B (C stretch).
"""
from __future__ import annotations

from app.models import Arm, Decision, Segment


def decide(segments: list[Segment], arm: Arm, policy_version: str) -> list[Decision]:
    return []
