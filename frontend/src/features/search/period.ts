import { dayjs, todayYmd } from "../../lib/dates";

export type PeriodPreset = "today" | "7d" | "30d" | "custom";
export type Period = [string | null, string | null]; // YYYY-MM-DD, даты Красноярска

const DAYS: Record<Exclude<PeriodPreset, "custom">, number> = { today: 0, "7d": 6, "30d": 29 };

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
