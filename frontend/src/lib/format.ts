const nf = new Intl.NumberFormat("ru-RU");

/** 5400 → «5 400» */
export const fmtNumber = (n: number) => nf.format(n);

/** plural(5, ["публикация", "публикации", "публикаций"]) → «публикаций» */
export function plural(n: number, forms: [string, string, string]): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return forms[0];
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return forms[1];
  return forms[2];
}

export const publications = (n: number) => `${fmtNumber(n)} ${plural(n, ["публикация", "публикации", "публикаций"])}`;

export const sourcesCount = (n: number) => `${fmtNumber(n)} ${plural(n, ["источник", "источника", "источников"])}`;
