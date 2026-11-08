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
  ended_at?: number | null; // epoch s the turn's speech ended (live audio only)
  audio?: string | null; // replay only: the turn's WAV, served at /demo/audio/<audio>
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
  source?: string | null; // "replay:<scenario>", "phone" (a real Twilio call) or "mic" (browser mic)
}

export interface SmsPayload {
  message_id: string;
  template_id: string;
  status: "queued" | "sent" | "delivered" | "failed";
  latency_ms?: number | null; // alerts: end of the flagged turn's speech -> gateway accepted the text
  error_code?: string | null; // Twilio ErrorCode ("30034": carriers block an unregistered A2P 10DLC number)
}

// The pipeline's verdict on one transcript turn. ai "unavailable": the model call failed, rules only;
// "off": arm B or a subscriber turn.
export interface TurnPayload {
  seq: number;
  speaker: Speaker;
  ai: "request" | "no_request" | "unavailable" | "off";
  score: number | null;
  category: RiskEvent["category"] | null;
  flagged_by: "rule" | "intent" | null;
  decided_ms: number;
}

// GET /results/latest (backend/app/models.py Results): eval counts per arm over one batch of scripted calls.
export interface ArmCounts {
  TP: number;
  FP: number;
  FN: number;
  TN: number;
  hard_benign_fp: number;
  hard_benign_n: number;
}
export interface Results {
  batch: string;
  source: "script";
  arms: Record<string, ArmCounts>;
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
  | { event_id: string; session_ref: string | null; type: "consent"; payload: { state: ConsentState } }
  | { event_id: string; session_ref: string | null; type: "turn"; payload: TurnPayload };
