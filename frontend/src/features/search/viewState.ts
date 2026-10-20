// Какой экран итога показать — одна функция на всё приложение (FE-06), чтобы состояния не разъехались.
import type { S } from "../../api/client";
import { PLATFORM_NAME } from "../../lib/platforms";
import { isFinal } from "./status";

export type ViewState =
  | "running"
  | "running_with_results"
  | "ok"
  | "partial"
  | "empty"
  | "failed"
  | "failed_with_results"
  | "cancelled";

/**
 * `found` — сколько система нашла: counts.total + counts.excluded.
 * Исключённые вручную учитываем, иначе «исключил всё» выглядело бы как «ничего не найдено».
 */
export function viewState(s: S["Search"], noGlobal: NoGlobal = NONE): ViewState {
  const found = foundCount(s);
  if (!isFinal(s.status)) return found > 0 ? "running_with_results" : "running";
  if (s.status === "failed") return found > 0 ? "failed_with_results" : "failed";
  if (s.status === "cancelled") return "cancelled";
  if (found === 0) return "empty"; // completed или partial без результатов
  // partial только из-за «Везде» на площадке без поиска по всей площадке — это не сбой
  return s.status === "partial" && failedTargets(s, noGlobal).length > 0 ? "partial" : "ok";
}

export const foundCount = (s: S["Search"]) => s.counts.total + s.counts.excluded;

/** Вкладки и список показываем, пока поиск идёт или когда в подборке есть что показать. */
export const showsResults = (s: S["Search"]) => !isFinal(s.status) || foundCount(s) > 0;

/** Площадки, где нет поиска по всей площадке (`global_mode=false` в GET /platforms). */
export type NoGlobal = ReadonlySet<S["Platform"]>;
const NONE: NoGlobal = new Set();

/**
 * Цель «поиск по площадке» там, где площадка его не умеет (MAX в режиме «Везде»).
 * Сервер такие цели больше не создаёт, но они есть в старых поисках из истории — показываем
 * их как пометку, а не как ошибку.
 */
export const isUnsupportedGlobal = (t: S["SearchTarget"], noGlobal: NoGlobal) =>
  t.kind === "platform_search" && t.status !== "done" && noGlobal.has(t.platform);

/** Упавшие цели — без «не поддерживается» (их повторять бессмысленно). */
export const failedTargets = (s: S["Search"], noGlobal: NoGlobal = NONE) =>
  s.targets.filter((t) => t.status === "failed" && !isUnsupportedGlobal(t, noGlobal));

/** Причина неудачи поиска: текст первой упавшей цели, иначе — предупреждение сервера. */
export function failureReason(s: S["Search"], noGlobal: NoGlobal = NONE): string | null {
  return failedTargets(s, noGlobal).find((t) => t.error?.message)?.error?.message ?? s.warnings[0] ?? null;
}

/** Название цели для людей: у поиска по площадке сервер присылает код («NEWS»). */
export const targetName = (t: S["SearchTarget"]) =>
  t.kind === "platform_search" ? `Поиск по всей площадке: ${PLATFORM_NAME[t.platform]}` : t.name;
