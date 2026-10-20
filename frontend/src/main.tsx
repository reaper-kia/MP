import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./styles.css";
import "./motion.css";

import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./lib/dates";
import { cssVariablesResolver, theme } from "./theme";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

async function enableMocks() {
  // VITE_MOCKS=1 (npm run dev:mocks или VITE_MOCKS=1 в окружении) — все /api/v1 отвечает MSW из src/mocks, бэкенд не нужен
  if (import.meta.env.VITE_MOCKS !== "1") return;
  const { worker } = await import("./mocks/browser");
  await worker.start({ onUnhandledFrame: "bypass", quiet: true });
}

enableMocks().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      {/* тема: как в системе, переключатель в шапке запоминает выбор */}
      <MantineProvider theme={theme} cssVariablesResolver={cssVariablesResolver} defaultColorScheme="auto">
        <Notifications position="top-right" />
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </MantineProvider>
    </StrictMode>,
  );
});
