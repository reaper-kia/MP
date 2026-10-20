import react from "@vitejs/plugin-react";
import { msw } from "msw/vite";
import { defineConfig } from "vite";

// В dev-режиме Vite проксирует /api: по умолчанию в Prism-мок (npm run mock, 127.0.0.1:4010 — не localhost: на Windows он резолвится в ::1, а Prism слушает IPv4),
// на gateway — VITE_API_TARGET=http://localhost:8000 npm run dev.
// npm run dev:mocks (режим mocks → VITE_MOCKS=1) — вместо прокси отвечает MSW в браузере.
const API_TARGET = process.env.VITE_API_TARGET ?? "http://127.0.0.1:4010";

export default defineConfig(({ mode }) => ({
  // worker-only: плагин только отдаёт mockServiceWorker.js, запуск — в src/main.tsx
  plugins: [react(), ...(mode === "mocks" ? [msw({ mode: "worker-only" })] : [])],
  define: mode === "mocks" ? { "import.meta.env.VITE_MOCKS": JSON.stringify("1") } : {},
  build: {
    rollupOptions: {
      output: {
        // библиотеки — отдельными файлами: кэшируются между выкладками, страницы грузятся по требованию (FE-16)
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/[\/]@mantine[\/]dates[\/]/.test(id)) return "mantine-dates";
          if (/[\/]@mantine[\/]/.test(id)) return "mantine";
          if (/[\/](react|react-dom|react-router|scheduler)[\/]/.test(id)) return "react";
          if (/[\/]@tanstack[\/]/.test(id)) return "query";
          return undefined; // мелочь (dayjs, clsx…) — куда решит сборщик
        },
      },
    },
  },
  server: {
    port: 5173,
    // сборка расширения (npm run build:ext) не должна перезагружать dev-сервер
    watch: { ignored: ["**/dist-ext/**"] },
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true },
    },
  },
}));
