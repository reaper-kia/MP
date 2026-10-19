import type { S } from "../../api/client";

export const FINAL_STATUSES: S["SearchStatus"][] = ["completed", "partial", "failed", "cancelled"];

export const isFinal = (status: S["SearchStatus"] | undefined) => !!status && FINAL_STATUSES.includes(status);

export function stageText(search: S["Search"]): string {
  const { targets_finished, targets_total } = search.progress;
  switch (search.stage) {
    case "queued":
      return "В очереди…";
    case "analyzing_query":
      return "Разбираем запрос…";
    case "collecting":
      return `Собираем публикации — ${targets_finished} из ${targets_total} источников`;
    case "scoring":
      return "Проверяем связь с запросом…";
    case "grouping":
      return "Группируем одинаковые новости…";
    case "done":
      return "Готово";
  }
}

// Цвета статусов — одни во всём приложении (токены дизайнера подтянем в FE-11):
// идёт — синий, готово — зелёный, частично — жёлтый, ошибка — красный, остановлен / пусто — серый.
export const STATUS_COLOR = {
  running: "blue",
  ok: "green",
  partial: "yellow",
  failed: "red",
  neutral: "gray",
} as const;

export const SEARCH_STATUS: Record<S["SearchStatus"], { label: string; color: string }> = {
  queued: { label: "В очереди", color: STATUS_COLOR.neutral },
  running: { label: "Идёт", color: STATUS_COLOR.running },
  completed: { label: "Готово", color: STATUS_COLOR.ok },
  partial: { label: "Частично", color: STATUS_COLOR.partial },
  failed: { label: "Не выполнен", color: STATUS_COLOR.failed },
  cancelled: { label: "Остановлен", color: STATUS_COLOR.neutral },
};

export const TARGET_STATUS: Record<S["TargetStatus"], { label: string; color: string }> = {
  pending: { label: "В очереди", color: STATUS_COLOR.neutral },
  running: { label: "Обрабатывается", color: STATUS_COLOR.running },
  done: { label: "Готово", color: STATUS_COLOR.ok },
  empty: { label: "Нет публикаций", color: STATUS_COLOR.neutral },
  failed: { label: "Не удалось", color: STATUS_COLOR.failed },
  skipped: { label: "Пропущен", color: STATUS_COLOR.neutral },
};
