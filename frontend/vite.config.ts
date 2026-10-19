import react from "@vitejs/plugin-react";
import { msw } from "msw/vite";
import { defineConfig } from "vite";

// В dev-режиме Vite проксирует /api: по умолчанию в Prism-мок (npm run mock, 127.0.0.1:4010 — не localhost: на Windows он резолвится в ::1, а Prism слушает IPv4),
// на gateway — VITE_API_TARGET=http://localhost:8000 npm run dev.
// npm run dev:mocks (VITE_MOCKS=1 из .env.mocks) — вместо прокси отвечает MSW в браузере.
const API_TARGET = process.env.VITE_API_TARGET ?? "http://127.0.0.1:4010";

export default defineConfig(({ mode }) => ({
  // worker-only: плагин только отдаёт mockServiceWorker.js, запуск — в src/main.tsx
  plugins: [react(), ...(mode === "mocks" ? [msw({ mode: "worker-only" })] : [])],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
    },
  },
}));
