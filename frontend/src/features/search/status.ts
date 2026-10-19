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

// Цвета статусов — одни во всём приложении (токены дизайнера подтянем в FE-11)
export const TARGET_STATUS: Record<S["TargetStatus"], { label: string; color: string }> = {
  pending: { label: "В очереди", color: "gray" },
  running: { label: "Обрабатывается", color: "blue" },
  done: { label: "Готово", color: "green" },
  empty: { label: "Нет публикаций", color: "gray" },
  failed: { label: "Не удалось", color: "red" },
  skipped: { label: "Пропущен", color: "gray" },
};
