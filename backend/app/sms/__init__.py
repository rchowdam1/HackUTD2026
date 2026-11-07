"""SMS gateways (Track B owns after the skeleton merges).

Skeleton stub: SimulatedGateway logs and returns a fake id.
"""
from __future__ import annotations

import logging
import uuid

from app.models import SmsGateway

log = logging.getLogger(__name__)


class SimulatedGateway:
    def send(self, template_id: str, session_ref: str) -> str:
        message_id = f"SIM{uuid.uuid4().hex[:12]}"
        log.info("simulated sms %s template=%s session=%s", message_id, template_id, session_ref)
        return message_id


def get_gateway() -> SmsGateway:
    return SimulatedGateway()
