// Настройки расширения (FE-17): адрес сервера, режим и период по умолчанию — в chrome.storage.local.
import type { S } from "../api/client";

export interface ExtSettings {
  server: string;
  mode: S["SearchParams"]["mode"];
  days: 7 | 30;
}

/** Адрес из сборки: VITE_API_URL=http://адрес npm run build:ext. */
export const DEFAULT_SERVER = (import.meta.env.VITE_API_URL || "http://109.196.167.204:8080").replace(/\/+$/, "");

export const DEFAULT_SETTINGS: ExtSettings = { server: DEFAULT_SERVER, mode: "selected", days: 30 };

export async function loadSettings(): Promise<ExtSettings> {
  const saved = (await chrome.storage.local.get("settings")).settings as Partial<ExtSettings> | undefined;
  return { ...DEFAULT_SETTINGS, ...saved };
}

export async function saveSettings(s: ExtSettings): Promise<void> {
  await chrome.storage.local.set({ settings: s });
}

/** "http://1.2.3.4:8080/путь" → "http://1.2.3.4:8080/*" — шаблон для host-разрешения. */
export const originPattern = (server: string) => `${new URL(server).origin}/*`;
