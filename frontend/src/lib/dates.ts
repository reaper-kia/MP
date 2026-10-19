import dayjs from "dayjs";
import "dayjs/locale/ru";
import customParseFormat from "dayjs/plugin/customParseFormat";
import timezone from "dayjs/plugin/timezone";
import utc from "dayjs/plugin/utc";

// Все *_at приходят в UTC, показываем в Красноярске.
// Даты периода (YYYY-MM-DD) — «календарные» даты Красноярска, в UTC не переводим.
export const TZ = "Asia/Krasnoyarsk";

dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.extend(customParseFormat);
dayjs.locale("ru");
dayjs.tz.setDefault(TZ);

export { dayjs };

/** "2026-10-15T03:20:00Z" → "15.10.2026, 10:20" (Красноярск). null → null. */
export function fmtDateTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  return dayjs.utc(iso).tz(TZ).format("DD.MM.YYYY, HH:mm");
}

/** "2026-10-15" → "15.10.2026". */
export function fmtDate(ymd: string): string {
  return dayjs(ymd, "YYYY-MM-DD", true).format("DD.MM.YYYY");
}

/** Сегодня по Красноярску как "YYYY-MM-DD". */
export function todayYmd(): string {
  return dayjs().tz(TZ).format("YYYY-MM-DD");
}
