// Выбор источников для режима «Только мои источники» хранится в localStorage,
// чтобы не выбирать заново при каждом поиске. null — «по умолчанию»: все активные.
const KEY = "mp.selectedSourceIds";

export function loadSelection(): string[] | null {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : null;
  } catch {
    return null;
  }
}

export function saveSelection(ids: string[] | null) {
  try {
    if (ids === null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, JSON.stringify(ids));
  } catch {
    // нет доступа к хранилищу — выбор просто не запомнится
  }
}
