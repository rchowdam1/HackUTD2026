import type { ConsentState, Event, SmsMode } from "./types";

// What GET /state returns: current values plus every event since the latest session running/reset.
export interface Snapshot {
  sms_mode: SmsMode;
  wrong_count: number;
  consent: ConsentState | null;
  events: Event[];
}

// Console registers these: any 401 returns to login; other failures surface as a visible error.
let handlers = { unauthorized: () => {}, error: (_message: string) => {} };
export function onFailure(h: typeof handlers) {
  handlers = h;
}

// Operator request; resolves to the response only when it is OK, otherwise reports and resolves null.
async function call(action: string, path: string, body?: unknown, method = "POST"): Promise<Response | null> {
  let r: Response;
  try {
    r = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    handlers.error(`${action} failed (network error)`);
    return null;
  }
  if (r.status === 401) handlers.unauthorized();
  else if (!r.ok) handlers.error(`${action} failed (HTTP ${r.status})`);
  return r.ok ? r : null;
}

// Resolves to an error message for the login form, or null on success.
export async function login(password: string): Promise<string | null> {
  try {
    const r = await fetch("/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
    if (r.ok) return null;
    if (r.status === 429) return `Too many attempts, try again in ${r.headers.get("Retry-After") ?? "a few"} s`;
    return r.status === 401 ? "Wrong password" : `Login failed (HTTP ${r.status})`;
  } catch {
    return "Login failed (network error)";
  }
}
export const loggedIn = async () => (await fetch("/aggregates")).ok;
export const logout = () => call("Log out", "/logout");
export const runScenario = (id: "clinic" | "bank" | "family") => call(`Run ${id}`, `/demo/run/${id}`);
export const endCall = () => call("End call", "/demo/end-call");
export const reset = () => call("Reset", "/demo/reset");
export const setSmsMode = (mode: SmsMode) => call("SMS mode change", "/demo/sms-mode", { mode });
export const simulateReply = (body: string) => call(`Simulated ${body} reply`, "/sms/simulate-inbound", { body });
export const setOptIn = (opt_in: boolean) => call("Opt-in choice", "/sms/consent", { opt_in });

// Background read: null on any failure, without an error banner (401 still returns to login).
async function read<T>(path: string): Promise<T | null> {
  const r = await fetch(path).catch(() => null);
  if (r?.status === 401) handlers.unauthorized();
  return r?.ok ? r.json() : null;
}
export const snapshot = () => read<Snapshot>("/state");

const textCache = new Map<string, Promise<string | null>>();
export function templateText(id: string): Promise<string | null> {
  if (!textCache.has(id)) {
    const text = fetch(`/sms/templates/${encodeURIComponent(id)}`).then((r) => (r.ok ? r.json().then((j) => j.text) : null));
    textCache.set(id, text);
    text.then((t) => t === null && textCache.delete(id), () => textCache.delete(id));
  }
  return textCache.get(id)!;
}

// EventSource retries on its own after a dropped connection, but gives up (CLOSED) on an HTTP error
// such as 401; then we probe via onError(closed=true) and reconnect ourselves.
export function subscribe(h: { event: (e: Event) => void; open: () => void; error: (closed: boolean) => void }): () => void {
  let source: EventSource;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const connect = () => {
    source = new EventSource("/events/stream");
    source.onopen = h.open;
    source.onmessage = (m) => h.event(JSON.parse(m.data));
    source.onerror = () => {
      const closed = source.readyState === EventSource.CLOSED;
      h.error(closed);
      if (closed) timer = setTimeout(connect, 3000);
    };
  };
  connect();
  return () => {
    clearTimeout(timer);
    source.close();
  };
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
