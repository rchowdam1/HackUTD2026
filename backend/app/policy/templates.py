"""SMS templates (PRD 19.5) from policy/<VERSION>/templates.yaml.

Usage: `from app.policy import templates; templates.get("ALERT-OTP-01")`.
Unknown ids raise KeyError.
"""
from __future__ import annotations

from app import policy

_data = policy.load("templates")
TEMPLATES: dict[str, str] = _data["templates"]
_ALERTS: dict[str, dict[str, str]] = _data["alerts"]


def get(template_id: str) -> str:
    return TEMPLATES[template_id]


def is_alert(template_id: str) -> bool:
    return template_id in _ALERTS


def followup_for(alert_id: str) -> str:
    """Follow-up template id for an ALERT-* id, e.g. ALERT-OTP-01 -> FU-OTP-01."""
    return _ALERTS[alert_id]["followup"]


def shared_for(alert_id: str) -> str:
    """Category-specific SHARED reply id for an ALERT-* id, e.g. ALERT-OTP-01 -> R-SHARED-OTP."""
    return _ALERTS[alert_id]["shared"]
