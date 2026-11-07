"""Intent model (stretch, arm C). Skeleton stub: always abstains."""
from __future__ import annotations

from app.models import Category, Segment


def classify(window: list[Segment]) -> Category | None:
    return None  # None = abstain
