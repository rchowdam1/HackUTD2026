import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Same-origin proxy to the FastAPI backend so the session cookie and SSE just work.
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
const proxied = ["/login", "/events", "/demo", "/results", "/aggregates", "/sms", "/health"];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(proxied.map((p) => [p, { target: backend, changeOrigin: true }])),
    fs: { allow: [".."] }, // event fixtures live in ../tests/fixtures
  },
});
