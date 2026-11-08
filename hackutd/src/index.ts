import { Spectrum } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";
import { timingSafeEqual } from "node:crypto";

// CallSafe <-> Photon Spectrum (iMessage) bridge (docs/photon-live.md, #68).
// Spectrum has no HTTP send API, so the Python backend calls this process instead:
//   POST http://127.0.0.1:$BRIDGE_PORT/send {to, text} -> {id}
// and every inbound text is forwarded to $BACKEND_URL/sms/inbound as {id, text, sender}.
// Both directions carry x-bridge-token: $PHOTON_BRIDGE_TOKEN. Never logs numbers or bodies.
// An inbound text is retried until the backend acknowledges it (2xx), so a STOP sent while the backend is
// down or restarting is delivered late, not lost. The backend dedupes by message id, so retries are safe.
const token = process.env.PHOTON_BRIDGE_TOKEN;
if (!token) throw new Error("PHOTON_BRIDGE_TOKEN is not set");
const backend = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const line = process.env.PHOTON_LINE; // optional: pin sends to this line (dedicated lines; ignored on shared pool)

const app = await Spectrum({
  projectId: process.env.PROJECT_ID!,
  projectSecret: process.env.PROJECT_SECRET!,
  providers: [imessage.config()],
});
const im = imessage(app);
const tokenBytes = Buffer.from(token);

function tokenOk(given: string | null): boolean {
  const g = Buffer.from(given ?? "");
  return g.length === tokenBytes.length && timingSafeEqual(g, tokenBytes);
}

Bun.serve({
  hostname: "127.0.0.1",
  port: Number(process.env.BRIDGE_PORT || 8787),
  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === "/health") return Response.json({ ok: true });
    if (req.method !== "POST" || url.pathname !== "/send") return new Response("not found", { status: 404 });
    if (!tokenOk(req.headers.get("x-bridge-token"))) return new Response("forbidden", { status: 403 });
    const { to, text } = (await req.json()) as { to: string; text: string };
    try {
      const user = await im.user(to);
      const space = line ? await im.space.create(user, { phone: line }) : await im.space.create(user);
      const sent = await space.send(text);
      return Response.json({ id: sent?.id ?? `spectrum-${crypto.randomUUID()}` });
    } catch (err) {
      const reason = err instanceof Error ? err.message.replace(/\+?\d{7,}/g, "<number>") : "unknown error";
      console.error("bridge send failed:", reason);
      return Response.json({ error: "send failed" }, { status: 502 });
    }
  },
});
console.log("bridge: listening on 127.0.0.1:" + (process.env.BRIDGE_PORT || 8787));

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// POST one inbound text until the backend acknowledges it. 4xx (bad token, malformed) won't improve on
// retry, so it is logged and dropped; network errors and 5xx back off up to 30 s and try again.
async function forward(body: string): Promise<void> {
  for (let attempt = 0; ; attempt++) {
    try {
      const r = await fetch(`${backend}/sms/inbound`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-bridge-token": token! },
        body,
      });
      if (r.ok) return;
      if (r.status < 500) {
        console.error(`bridge: backend rejected inbound (HTTP ${r.status}); not retrying`);
        return;
      }
      console.error(`bridge: backend failed inbound (HTTP ${r.status}); retrying`);
    } catch {
      console.error("bridge: backend unreachable for inbound; retrying");
    }
    await sleep(Math.min(30_000, 500 * 2 ** attempt));
  }
}

for await (const [, message] of app.messages) {
  if (message.direction === "outbound" || message.content.type !== "text") continue;
  // In order, one at a time: a later YES must not overtake an earlier STOP.
  await forward(JSON.stringify({ id: message.id, text: message.content.text, sender: message.sender?.id ?? null }));
}
