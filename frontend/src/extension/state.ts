// Состояние поиска расширения — в chrome.storage.session: окошко закрывается при клике мимо,
// а поиск идёт в service worker; открыл окошко снова — видишь ход или результат (FE-17).
import type { S } from "../api/client";

export interface RunState {
  query: string;
  mode: S["SearchParams"]["mode"];
  days: 7 | 30;
  periodFrom: string;
  periodTo: string;
  /** Адрес сервера, на котором запущен поиск, — для ссылки «Открыть подборку на сайте». */
  server: string;
  searchId: string | null;
  /** Последний ответ GET /searches/{id}; null — поиск ещё создаётся. */
  search: S["Search"] | null;
  /** Ошибка запуска или опроса — текст для человека. */
  error: string | null;
  startedAt: number;
}

export async function loadRun(): Promise<RunState | null> {
  return ((await chrome.storage.session.get("run")).run as RunState | undefined) ?? null;
}

export async function saveRun(run: RunState | null): Promise<void> {
  if (run) await chrome.storage.session.set({ run });
  else await chrome.storage.session.remove("run");
}

/** Сообщения окошко → service worker. */
export type ExtMessage =
  | { type: "start"; query: string; mode: S["SearchParams"]["mode"]; days: 7 | 30 }
  | { type: "cancel" }
  | { type: "reset" };

/** RunState.error, когда сервер не ответил вовсе (сеть, неверный адрес, нет host-разрешения). */
export const NO_CONNECTION = "NO_CONNECTION";
