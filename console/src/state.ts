import type { Snapshot } from "./api";
import type { ConsentState, Decision, Event, RiskEvent, Segment, SessionPayload, SmsMode, SmsPayload } from "./types";

// One phone-frame bubble: a text we sent, or a keyword the phone sent back.
export type Bubble = { kind: "out"; sms: SmsPayload } | { kind: "in"; keyword: string; id: string };

export interface State {
  session: SessionPayload | null;
  smsMode: SmsMode;
  segments: Segment[];
  risks: RiskEvent[];
  decisions: Decision[];
  bubbles: Bubble[];
  wrongCount: number;
  consent: ConsentState | null;
}

export const initial: State = {
  session: null,
  smsMode: "simulated",
  segments: [],
  risks: [],
  decisions: [],
  bubbles: [],
  wrongCount: 0,
  consent: null,
};

export type Action = Event | { type: "sms_mode"; mode: SmsMode } | { type: "hydrate"; snapshot: Snapshot; after: Event[] };

export function reduce(s: State, a: Action): State {
  switch (a.type) {
    case "session": {
      const p = a.payload;
      if (p.state === "running") {
        return { ...s, session: p, smsMode: p.sms_mode ?? s.smsMode, segments: [], risks: [], decisions: [], bubbles: [] };
      }
      if (p.state === "reset") return { ...s, session: p, segments: [], risks: [], decisions: [], bubbles: [] };
      return { ...s, session: { ...p, sms_mode: p.sms_mode ?? s.session?.sms_mode ?? null } };
    }
    case "segment":
      return { ...s, segments: [...s.segments.filter((x) => x.seq !== a.payload.seq), a.payload].sort((x, y) => x.seq - y.seq) };
    case "risk_event":
      return { ...s, risks: [...s.risks, a.payload] };
    case "decision":
      return { ...s, decisions: [...s.decisions, a.payload] };
    case "sms": {
      const sms = a.payload;
      const i = sms.message_id ? s.bubbles.findIndex((b) => b.kind === "out" && b.sms.message_id === sms.message_id) : -1;
      if (i < 0) return { ...s, bubbles: [...s.bubbles, { kind: "out", sms }] };
      const bubbles = s.bubbles.slice();
      bubbles[i] = { kind: "out", sms };
      return { ...s, bubbles };
    }
    case "reply":
      return {
        ...s,
        wrongCount: Math.max(s.wrongCount, a.payload.wrong_count), // WRONG total never decreases
        bubbles: [...s.bubbles, { kind: "in", keyword: a.payload.keyword, id: a.event_id }],
      };
    case "consent":
      return { ...s, consent: a.payload.state };
    case "sms_mode":
      return { ...s, smsMode: a.mode };
    case "hydrate": {
      // Rebuild from GET /state, then apply live events that arrived after it, minus duplicates.
      const { snapshot: snap, after } = a;
      const seen = new Set(snap.events.map((e) => e.event_id));
      const replayed = snap.events.reduce(reduce, { ...initial, wrongCount: Math.max(s.wrongCount, snap.wrong_count) });
      const current = { ...replayed, smsMode: snap.sms_mode, consent: snap.consent }; // snapshot values are newer than its events
      return after.filter((e) => !seen.has(e.event_id)).reduce(reduce, current);
    }
  }
}
