import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// В dev-режиме Vite проксирует /api: по умолчанию в Prism-мок (npm run mock, 127.0.0.1:4010 — не localhost: на Windows он резолвится в ::1, а Prism слушает IPv4),
// на gateway — VITE_API_TARGET=http://localhost:8000 npm run dev.
const API_TARGET = process.env.VITE_API_TARGET ?? "http://127.0.0.1:4010";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
    },
  },
});
