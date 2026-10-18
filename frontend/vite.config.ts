import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// В dev-режиме (npm run dev) Vite проксирует API и WebSocket в локальный gateway,
// поэтому фронт и бэк живут на одном origin и refresh-cookie работает без CORS-плясок.
const GATEWAY = process.env.GATEWAY_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": GATEWAY,
      "/health": GATEWAY,
      "/ws": { target: GATEWAY.replace(/^http/, "ws"), ws: true },
    },
  },
});
