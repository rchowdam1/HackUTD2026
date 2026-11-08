import type { Event, Results, SmsMode } from "./types";

async function post(path: string, body?: unknown): Promise<Response> {
  return fetch(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const login = async (password: string) => (await post("/login", { password })).ok;
export const loggedIn = async () => (await fetch("/aggregates")).ok;
export const runScenario = (id: "clinic" | "bank") => post(`/demo/run/${id}`);
export const endCall = () => post("/demo/end-call");
export const reset = () => post("/demo/reset");
export const setSmsMode = (mode: SmsMode) => post("/demo/sms-mode", { mode });
export const simulateReply = (body: string) => post("/sms/simulate-inbound", { body });

export async function results(): Promise<Results> {
  const r = await fetch("/results/latest");
  return r.ok ? r.json() : { status: "pending" };
}

export async function wrongCount(): Promise<number> {
  const r = await fetch("/aggregates");
  if (!r.ok) return 0;
  const agg: { replies: { keyword: string; count: number }[] } = await r.json();
  return agg.replies.filter((x) => x.keyword === "WRONG").reduce((n, x) => n + x.count, 0);
}

const textCache = new Map<string, Promise<string | null>>();
export function templateText(id: string): Promise<string | null> {
  if (!textCache.has(id)) {
    textCache.set(id, fetch(`/sms/templates/${encodeURIComponent(id)}`).then((r) => (r.ok ? r.json().then((j) => j.text) : null)));
  }
  return textCache.get(id)!;
}

export function subscribe(onEvent: (e: Event) => void): () => void {
  const source = new EventSource("/events/stream");
  source.onmessage = (m) => onEvent(JSON.parse(m.data));
  return () => source.close();
}

// Fixture replay (?fixtures): Track A's example events, in event_id order, without a backend.
const fixtureModules = import.meta.glob("../../tests/fixtures/events/*.json", { eager: true, import: "default" });
export function replayFixtures(onEvent: (e: Event) => void, stepMs = 700): () => void {
  const events = (Object.values(fixtureModules) as Event[])
    .filter((e) => !(e.type === "session" && e.payload.state === "reset"))
    .sort((a, b) => a.event_id.localeCompare(b.event_id));
  const timers = events.map((e, i) => setTimeout(() => onEvent(e), (i + 1) * stepMs));
  return () => timers.forEach(clearTimeout);
}
