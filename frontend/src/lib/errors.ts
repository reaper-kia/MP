// Тексты ошибок API для пользователя — по таблице «Коды ошибок» в docs/tasks/FE.md.
import { ApiError } from "../api/client";

const BY_CODE: Record<string, string> = {
  UNSUPPORTED_URL: "Это не похоже на ссылку на группу VK, OK или канал MAX",
  SOURCE_NOT_FOUND: "Такой группы или канала не нашлось — проверьте ссылку",
  SOURCE_PRIVATE: "Группа закрыта — публикации недоступны",
  SOURCE_ALREADY_EXISTS: "Этот источник уже есть в списке",
  RATE_LIMITED: "Слишком много запросов к площадке, подождите минуту",
  SEARCH_NOT_FINISHED: "Дождитесь окончания поиска",
  SERVICE_UNAVAILABLE: "Сервис временно недоступен. Повторите попытку",
  UPSTREAM_ERROR: "Сервис временно недоступен. Повторите попытку",
};

/** Где случилась ошибка — от этого зависит текст для 501 NOT_IMPLEMENTED. */
export type ErrorContext = "source" | "export" | "import";

// 501 — «ещё не сделано», а не «сломалось». Временные тексты до UI-04.
const NOT_IMPLEMENTED: Record<ErrorContext | "default", string> = {
  source: "Эта площадка пока не подключена — сейчас можно добавлять только группы ВКонтакте",
  export: "Выгрузка в этом формате пока недоступна",
  import: "Загрузка списка из Excel пока недоступна",
  default: "Эта возможность пока недоступна",
};

/** Текст для уведомления. Для неизвестных кодов — message с сервера (он по-русски). */
export function errorText(err: unknown, context?: ErrorContext): string {
  if (err instanceof ApiError) {
    if (err.code === "NOT_IMPLEMENTED") return NOT_IMPLEMENTED[context ?? "default"];
    // 503 PLATFORM_UNAVAILABLE: сервер пишет причину сам («ВКонтакте: не настроен доступ…») — показываем её
    if (err.code === "PLATFORM_UNAVAILABLE") return err.message || "Площадка сейчас недоступна, попробуйте позже";
    if (err.status >= 500 && !BY_CODE[err.code]) return BY_CODE.SERVICE_UNAVAILABLE;
    return BY_CODE[err.code] ?? err.message;
  }
  return "Нет связи с сервером. Повторите попытку";
}

/** 422 → { поле: текст } по details[].field. Пусто, если ошибка не про поля. */
export function fieldErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || err.status !== 422) return {};
  const out: Record<string, string> = {};
  for (const d of err.details) {
    if (typeof d.field === "string") out[d.field] = (typeof d.message === "string" && d.message) || err.message;
  }
  return out;
}
