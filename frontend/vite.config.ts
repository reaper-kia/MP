import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// В dev-режиме Vite проксирует /api: по умолчанию в Prism-мок (npm run mock, порт 4010),
// на gateway — VITE_API_TARGET=http://localhost:8000 npm run dev.
const API_TARGET = process.env.VITE_API_TARGET ?? "http://localhost:4010";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
    },
  },
});
