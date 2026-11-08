// Mirrors backend/app/models.py (PRD §19.4). Track A owns the contract.

export type Speaker = "caller" | "subscriber";

export interface Segment {
  session_ref: string | null;
  seq: number;
  speaker: Speaker;
  t_start_ms: number;
  t_end_ms: number;
  text: string;
  source: "asr" | "cached" | "script";
}

export interface RiskEvent {
  session_ref: string | null;
  event_type: string;
  source: "rule" | "intent";
  rule_id: string | null;
  category: "otp" | "payment" | "remote";
  span_seq: number[];
  confidence_class: "high" | "medium" | "low";
  policy_version: string;
  score: number | null; // intent events: the model's probability that the caller asked
  match_spans: [number, number][]; // rule events: [start, end) offsets into segment span_seq[-1]
}

export interface Decision {
  session_ref: string | null;
  level: "action_warning" | "none";
  template_id: string | null;
  followup_template_id: string | null;
  basis: string[];
  keyword_arm_would_fire: boolean;
  policy_version: string;
}

export type SmsMode = "real" | "simulated";

export type ConsentState = "invited" | "active" | "stopped";

export interface SessionPayload {
  state: "running" | "finished" | "reset";
  arm: "K" | "B" | "C" | null;
  sms_mode: SmsMode | null;
}

export interface SmsPayload {
  message_id: string;
  template_id: string;
  status: "queued" | "sent" | "delivered" | "failed";
}

export interface ReplyPayload {
  keyword: string;
  counted: boolean;
  wrong_count: number;
}

export type Event =
  | { event_id: string; session_ref: string | null; type: "session"; payload: SessionPayload }
  | { event_id: string; session_ref: string | null; type: "segment"; payload: Segment }
  | { event_id: string; session_ref: string | null; type: "risk_event"; payload: RiskEvent }
  | { event_id: string; session_ref: string | null; type: "decision"; payload: Decision }
  | { event_id: string; session_ref: string | null; type: "sms"; payload: SmsPayload }
  | { event_id: string; session_ref: string | null; type: "reply"; payload: ReplyPayload }
  | { event_id: string; session_ref: string | null; type: "consent"; payload: { state: ConsentState } };
