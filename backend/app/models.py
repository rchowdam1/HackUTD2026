"""Shared contracts (PRD §19.4). Track A owns this file.

Changes only via a `CONTRACT:` PR, additive fields with defaults.
"""
from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

Arm = Literal["K", "B", "C"]
SmsMode = Literal["real", "simulated"]
Speaker = Literal["caller", "subscriber"]
Category = Literal["otp", "payment", "remote"]
ConfidenceClass = Literal["high", "medium", "low"]


# --- Scenario files (Track C writes) ---------------------------------------

class Turn(BaseModel):
    speaker: Speaker
    text: str
    audio: str | None = None  # relative to audio/demo/, e.g. "<id>/t01.wav"


class Scenario(BaseModel):
    id: str
    set: Literal["dev", "demo", "H1"]
    label: Literal["scam", "benign"]
    hard_benign: bool = False
    category: Literal["otp", "payment", "remote", "none"]
    turns: list[Turn]


class TranscriptLine(BaseModel):
    """One entry of scenarios/demo/<id>/transcript.json (a JSON array of these)."""
    seq: int
    speaker: Speaker
    t_start_ms: int
    t_end_ms: int
    text: str


# --- Pipeline data ----------------------------------------------------------

class Segment(BaseModel):
    session_ref: str | None = None  # None when eval scores scripts directly
    seq: int
    speaker: Speaker
    t_start_ms: int = 0
    t_end_ms: int = 0
    text: str
    source: Literal["asr", "cached", "script"]


class RiskEvent(BaseModel):
    """Category wording only, never quoted call text."""
    session_ref: str | None = None
    event_type: str
    source: Literal["rule", "intent"]
    rule_id: str | None = None
    category: Category
    span_seq: list[int]
    confidence_class: ConfidenceClass
    policy_version: str
    score: float | None = None  # intent events: the model's probability that the caller asked (app.intent)


class Decision(BaseModel):
    session_ref: str | None = None
    level: Literal["action_warning", "none"]
    template_id: str | None = None
    followup_template_id: str | None = None
    basis: list[str] = Field(default_factory=list)  # rule / risk-event ids
    keyword_arm_would_fire: bool = False
    policy_version: str


# --- SSE event envelope + payloads -------------------------------------------

EventType = Literal["session", "segment", "risk_event", "decision", "sms", "reply", "consent"]


class SessionPayload(BaseModel):
    state: Literal["running", "finished", "reset"]
    arm: Arm | None = None
    sms_mode: SmsMode | None = None


class SmsPayload(BaseModel):
    message_id: str
    template_id: str
    status: Literal["queued", "sent", "delivered", "failed"]


class ReplyPayload(BaseModel):
    keyword: str
    counted: bool
    wrong_count: int


class ConsentPayload(BaseModel):
    state: Literal["invited", "active", "stopped"]


PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "session": SessionPayload,
    "segment": Segment,
    "risk_event": RiskEvent,
    "decision": Decision,
    "sms": SmsPayload,
    "reply": ReplyPayload,
    "consent": ConsentPayload,
}


class Event(BaseModel):
    event_id: str
    session_ref: str | None = None
    type: EventType
    payload: dict
    generation: int = 0  # session generation; stale generations are dropped (§19.10)

    def parsed_payload(self) -> BaseModel:
        return PAYLOAD_MODELS[self.type].model_validate(self.payload)


# --- Results file (Track C writes, Track B serves) ---------------------------

class ArmCounts(BaseModel):
    TP: int
    FP: int
    FN: int
    TN: int
    hard_benign_fp: int
    hard_benign_n: int


class Discordant(BaseModel):
    K_only: int
    B_only: int


class Results(BaseModel):
    batch: str
    source: Literal["script"] = "script"
    arms: dict[str, ArmCounts]
    discordant: Discordant | None = None


# --- SMS gateway (Track B implements) ---------------------------------------

@runtime_checkable
class SmsGateway(Protocol):
    def send(self, template_id: str, session_ref: str) -> str:
        """Send a template to the enrolled phone; return a message id.

        Must check consent first and refuse (raise) if not active.
        """
        ...

    def deliver(self, template_id: str, to: str | None = None, session_ref: str | None = None) -> str:
        """Send a template without the consent check (keyword replies, ENROLL); `to` None = DEMO_PHONE."""
        ...
