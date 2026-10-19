// Какой экран итога показать — одна функция на всё приложение (FE-06), чтобы состояния не разъехались.
import type { S } from "../../api/client";
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
export function viewState(s: S["Search"], found = foundCount(s)): ViewState {
  if (!isFinal(s.status)) return found > 0 ? "running_with_results" : "running";
  if (s.status === "failed") return found > 0 ? "failed_with_results" : "failed";
  if (s.status === "cancelled") return "cancelled";
  if (found === 0) return "empty"; // completed или partial без результатов
  return s.status === "partial" ? "partial" : "ok";
}

export const foundCount = (s: S["Search"]) => s.counts.total + s.counts.excluded;

/** Вкладки и список показываем, пока поиск идёт или когда в подборке есть что показать. */
export const showsResults = (s: S["Search"]) => !isFinal(s.status) || foundCount(s) > 0;

export const failedTargets = (s: S["Search"]) => s.targets.filter((t) => t.status === "failed");

/** Причина неудачи поиска: текст первой упавшей цели, иначе — предупреждение сервера. */
export function failureReason(s: S["Search"]): string | null {
  return failedTargets(s).find((t) => t.error?.message)?.error?.message ?? s.warnings[0] ?? null;
}
