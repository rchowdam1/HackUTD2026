"""SMS template lookup. Skeleton stub: a-templates loads policy/v1.0/templates.yaml.

Usage: `from app.policy import templates; templates.get("ALERT-OTP-01")`.
"""
from __future__ import annotations


def get(template_id: str) -> str:
    return f"Safe Signal: {template_id}"
