import { dayjs, fmtPeriod, todayYmd } from "../../lib/dates";

export type PeriodPreset = "today" | "7d" | "30d" | "year" | "custom";
export type Period = [string | null, string | null]; // YYYY-MM-DD, даты Красноярска

const DAYS: Record<Exclude<PeriodPreset, "custom">, number> = { today: 0, "7d": 6, "30d": 29, year: 364 };

/** Кнопки быстрого периода в поповере (макет v2: «Час · День · Месяц · Год»; час API не умеет — даты без времени). */
export const PRESETS: { value: Exclude<PeriodPreset, "custom">; short: string; label: string }[] = [
  { value: "today", short: "Сегодня", label: "Сегодня" },
  { value: "7d", short: "Неделя", label: "Последние 7 дней" },
  { value: "30d", short: "Месяц", label: "Последние 30 дней" },
  { value: "year", short: "Год", label: "Последний год" },
];

export function presetPeriod(preset: Exclude<PeriodPreset, "custom">): Period {
  const to = todayYmd();
  return [dayjs(to).subtract(DAYS[preset], "day").format("YYYY-MM-DD"), to];
}

/** Какой пресет соответствует периоду (для формы, открытой из search.params). */
export function detectPreset([from, to]: Period): PeriodPreset {
  if (!from || !to || to !== todayYmd()) return "custom";
  const found = (Object.keys(DAYS) as (keyof typeof DAYS)[]).find((p) => presetPeriod(p)[0] === from);
  return found ?? "custom";
}

/** Подпись на кнопке периода: «Последние 7 дней» или «12.10–19.10.2026». */
export function periodLabel(preset: PeriodPreset, [from, to]: Period): string {
  const p = PRESETS.find((x) => x.value === preset);
  if (p) return p.label;
  if (from && to) return fmtPeriod(from, to);
  return "Выберите даты";
}
