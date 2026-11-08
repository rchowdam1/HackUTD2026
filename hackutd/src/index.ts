import { Spectrum } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";

// Safe Signal <-> Photon Spectrum (iMessage) bridge (docs/photon-live.md, #68).
// Spectrum has no HTTP send API, so the Python backend calls this process instead:
//   POST http://127.0.0.1:$BRIDGE_PORT/send {to, text} -> {id}
// and every inbound text is forwarded to $BACKEND_URL/sms/inbound as {id, text, sender}.
// Both directions carry x-bridge-token: $PHOTON_BRIDGE_TOKEN. Never logs numbers or bodies.
const token = process.env.PHOTON_BRIDGE_TOKEN;
if (!token) throw new Error("PHOTON_BRIDGE_TOKEN is not set");
const backend = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const app = await Spectrum({
  projectId: process.env.PROJECT_ID!,
  projectSecret: process.env.PROJECT_SECRET!,
  providers: [imessage.config()],
});
const im = imessage(app);

Bun.serve({
  hostname: "127.0.0.1",
  port: Number(process.env.BRIDGE_PORT || 8787),
  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === "/health") return Response.json({ ok: true });
    if (req.method !== "POST" || url.pathname !== "/send") return new Response("not found", { status: 404 });
    if (req.headers.get("x-bridge-token") !== token) return new Response("forbidden", { status: 403 });
    const { to, text } = (await req.json()) as { to: string; text: string };
    try {
      const space = await im.space.create(await im.user(to));
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

for await (const [, message] of app.messages) {
  if (message.direction === "outbound" || message.content.type !== "text") continue;
  try {
    const r = await fetch(`${backend}/sms/inbound`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-bridge-token": token },
      body: JSON.stringify({ id: message.id, text: message.content.text, sender: message.sender?.id ?? null }),
    });
    if (!r.ok) console.error(`bridge: backend rejected inbound (HTTP ${r.status})`);
  } catch {
    console.error("bridge: backend unreachable for inbound");
  }
}
