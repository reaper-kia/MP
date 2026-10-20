// Общее для окошка и настроек расширения: тема сайта, React Query.
import "@mantine/core/styles.css";
import "../styles.css";
import "../motion.css";

import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

import "../lib/dates";
import { cssVariablesResolver, theme } from "../theme";

export function mount(node: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      {/* тема — как в системе: у расширения нет переключателя */}
      <MantineProvider theme={theme} cssVariablesResolver={cssVariablesResolver} defaultColorScheme="auto">
        <QueryClientProvider client={queryClient}>{node}</QueryClientProvider>
      </MantineProvider>
    </StrictMode>,
  );
}

/** Открыть страницу сайта в новой вкладке (окошко при этом закроется само). */
export const openTab = (url: string) => void chrome.tabs.create({ url });
