// MSW-обработчики всех ручек contracts/http/openapi.yaml поверх db.ts.
import { delay, http, HttpResponse } from "msw";

import type { S } from "../api/client";
import * as db from "./db";
import { PLATFORMS } from "./fixtures/catalog";
import { analyzeQuery } from "./fixtures/scenarios";

const API = "/api/v1";

function apiError(status: number, code: string, message: string, details: { field: string; message: string }[] = []) {
  return HttpResponse.json(
    { error: { code, message, request_id: `mock-${Date.now().toString(36)}`, details } },
    { status },
  );
}

function intParam(url: URL, name: string, def: number, max = Infinity) {
  const v = Number(url.searchParams.get(name));
  return Number.isFinite(v) && url.searchParams.has(name) ? Math.min(Math.max(0, Math.floor(v)), max) : def;
}

function page<T>(list: T[], url: URL) {
  const limit = intParam(url, "limit", 50, 200) || 50;
  const offset = intParam(url, "offset", 0);
  return { items: list.slice(offset, offset + limit), total: list.length, has_more: offset + limit < list.length };
}

function getSearch(id: string) {
  return db.searches.get(id);
}

const notFound = () => apiError(404, "SEARCH_NOT_FOUND", "Поиск не найден");

/** Сценарий «сбой»: с 4-й по 12-ю секунду поиска сервер «пропадает» — проверка «Нет связи с сервером». */
function connectionLost(rec: db.SearchRecord) {
  const t = Date.now() - rec.createdAt;
  return rec.params.query.toLowerCase().includes("сбой") && t > 4000 && t < 12000;
}

const REL_ORDER: Record<S["Relevance"], number> = { direct: 0, indirect: 1, disputed: 2, rejected: 3 };

function filterResults(list: S["Result"][], url: URL, opts: { target?: boolean; dateStatus?: boolean } = {}) {
  const sp = url.searchParams;
  const rel = sp.getAll("relevance") as S["Relevance"][];
  const relevance = rel.length ? rel : (["direct", "indirect", "disputed"] as S["Relevance"][]);
  const platforms = sp.getAll("platform");
  const targets = opts.target ? sp.getAll("target_id") : [];
  const dates = opts.dateStatus ? sp.getAll("date_status") : [];
  const includeExcluded = sp.get("include_excluded") === "true";
  return list.filter(
    (r) =>
      relevance.includes(r.relevance) &&
      (!platforms.length || platforms.includes(r.platform)) &&
      (!targets.length || targets.includes(r.found_by_target_id)) &&
      (!dates.length || dates.includes(r.date_status)) &&
      (includeExcluded || !r.excluded),
  );
}

function sortResults(list: S["Result"][], sort: string | null) {
  const time = (r: S["Result"]) => (r.published_at ? Date.parse(r.published_at) : null);
  const byDate = (dir: 1 | -1) => (a: S["Result"], b: S["Result"]) => {
    const ta = time(a);
    const tb = time(b);
    if (ta === null) return tb === null ? 0 : 1; // без даты — в конец
    if (tb === null) return -1;
    return (ta - tb) * dir;
  };
  if (sort === "date_desc") return [...list].sort(byDate(-1));
  if (sort === "date_asc") return [...list].sort(byDate(1));
  return [...list].sort((a, b) => REL_ORDER[a.relevance] - REL_ORDER[b.relevance] || b.score - a.score);
}

export const handlers = [
  // ── meta ──
  http.get(`${API}/platforms`, async () => {
    await delay(150);
    return HttpResponse.json(PLATFORMS);
  }),

  http.post(`${API}/query/analyze`, async ({ request }) => {
    await delay(400);
    const { query = "" } = ((await request.json().catch(() => ({}))) ?? {}) as Partial<S["QueryAnalyzeIn"]>;
    if (query.trim().length < 3 || query.length > 20000) {
      return apiError(422, "VALIDATION_ERROR", "Запрос должен быть от 3 до 20000 символов", [
        { field: "query", message: "От 3 до 20000 символов" },
      ]);
    }
    return HttpResponse.json(analyzeQuery(query));
  }),

  // ── источники ──
  http.get(`${API}/sources`, async ({ request }) => {
    await delay(200);
    const url = new URL(request.url);
    const platforms = url.searchParams.getAll("platform");
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const active = url.searchParams.get("is_active");
    const list = db.sources.filter(
      (s) =>
        (!platforms.length || platforms.includes(s.platform)) &&
        (!q || s.name.toLowerCase().includes(q) || s.url.toLowerCase().includes(q)) &&
        (active === null || String(s.is_active) === active),
    );
    return HttpResponse.json(page(list, url));
  }),

  http.post(`${API}/sources/resolve`, async ({ request }) => {
    await delay(600);
    const { url = "" } = ((await request.json().catch(() => ({}))) ?? {}) as Partial<S["SourceResolveIn"]>;
    const r = resolve(url);
    return r instanceof Response ? r : HttpResponse.json(r);
  }),

  http.post(`${API}/sources/import`, async () => {
    await delay(800);
    const report: S["SourceImportReport"] = {
      created: 2,
      duplicates: 1,
      failed: [{ row: 4, value: "https://example.com/abc", code: "UNSUPPORTED_URL", message: "Это не похоже на ссылку на группу VK, OK или канал MAX" }],
    };
    return HttpResponse.json(report);
  }),

  http.post(`${API}/sources`, async ({ request }) => {
    await delay(300);
    const body = ((await request.json().catch(() => ({}))) ?? {}) as Partial<S["SourceCreateIn"]>;
    const preview = resolve(body.url ?? "");
    if (preview instanceof Response) return preview;
    if (preview.existing_source_id) return apiError(409, "SOURCE_ALREADY_EXISTS", "Этот источник уже есть в списке");
    const now = new Date().toISOString();
    const source: S["Source"] = {
      id: crypto.randomUUID(),
      platform: preview.platform,
      external_id: preview.external_id,
      url: preview.url,
      name: body.name?.trim() || preview.name,
      city: preview.city,
      is_regional: body.is_regional ?? true,
      is_active: true,
      notes: body.notes ?? "",
      created_at: now,
      updated_at: now,
    };
    db.saveSources([source, ...db.sources]);
    return HttpResponse.json(source, { status: 201 });
  }),

  http.patch(`${API}/sources/:sourceId`, async ({ request, params }) => {
    await delay(200);
    const patch = ((await request.json().catch(() => ({}))) ?? {}) as S["SourceUpdateIn"];
    const current = db.sources.find((s) => s.id === params.sourceId);
    if (!current) return apiError(404, "SOURCE_NOT_FOUND", "Источник не найден");
    const next = { ...current, ...patch, updated_at: new Date().toISOString() };
    db.saveSources(db.sources.map((s) => (s.id === current.id ? next : s)));
    return HttpResponse.json(next);
  }),

  http.delete(`${API}/sources/:sourceId`, async ({ params }) => {
    await delay(200);
    if (!db.sources.some((s) => s.id === params.sourceId)) return apiError(404, "SOURCE_NOT_FOUND", "Источник не найден");
    db.saveSources(db.sources.filter((s) => s.id !== params.sourceId));
    return new HttpResponse(null, { status: 204 });
  }),

  // ── поиски ──
  http.post(`${API}/searches`, async ({ request }) => {
    await delay(300);
    const body = ((await request.json().catch(() => ({}))) ?? {}) as Partial<S["SearchCreateIn"]>;
    const details = validateSearch(body);
    if (details.length) return apiError(422, "SEARCH_INVALID_PARAMS", "Проверьте параметры поиска", details);
    const rec = db.createSearch(body as S["SearchCreateIn"]);
    return HttpResponse.json(db.snapshot(rec).search, { status: 202 });
  }),

  http.get(`${API}/searches`, async ({ request }) => {
    await delay(200);
    const url = new URL(request.url);
    const list = [...db.searches.values()]
      .sort((a, b) => b.createdAt - a.createdAt)
      .map((rec): S["SearchSummary"] => {
        const { search } = db.snapshot(rec);
        const { id, status, params, counts, created_at, finished_at } = search;
        return { id, status, params, counts, created_at, finished_at };
      });
    const { items, has_more } = page(list, url);
    return HttpResponse.json({ items, has_more });
  }),

  http.get(`${API}/searches/:searchId`, async ({ params }) => {
    await delay(120);
    const rec = getSearch(params.searchId as string);
    if (rec && connectionLost(rec)) return HttpResponse.error();
    return rec ? HttpResponse.json(db.snapshot(rec).search) : notFound();
  }),

  http.post(`${API}/searches/:searchId/retry`, async ({ request, params }) => {
    await delay(200);
    const rec = getSearch(params.searchId as string);
    if (!rec) return notFound();
    if (!db.snapshot(rec).final) return apiError(409, "SEARCH_NOT_FINISHED", "Дождитесь окончания поиска");
    const body = ((await request.json().catch(() => ({}))) ?? {}) as { target_ids?: string[] };
    db.retry(rec, body.target_ids);
    return HttpResponse.json(db.snapshot(rec).search, { status: 202 });
  }),

  http.post(`${API}/searches/:searchId/cancel`, async ({ params }) => {
    await delay(200);
    const rec = getSearch(params.searchId as string);
    if (!rec) return notFound();
    if (!db.snapshot(rec).final) db.cancel(rec);
    return HttpResponse.json(db.snapshot(rec).search);
  }),

  // ── подборка ──
  http.get(`${API}/searches/:searchId/results`, async ({ request, params }) => {
    await delay(250);
    const rec = getSearch(params.searchId as string);
    if (!rec) return notFound();
    if (connectionLost(rec)) return HttpResponse.error();
    const url = new URL(request.url);
    const list = sortResults(filterResults(db.snapshot(rec).visible, url, { target: true, dateStatus: true }), url.searchParams.get("sort"));
    return HttpResponse.json(page(list, url));
  }),

  http.get(`${API}/searches/:searchId/groups`, async ({ request, params }) => {
    await delay(250);
    const rec = getSearch(params.searchId as string);
    if (!rec) return notFound();
    const url = new URL(request.url);
    const visible = db.snapshot(rec).visible;
    const includeExcluded = url.searchParams.get("include_excluded") === "true";
    const matched = sortResults(filterResults(visible, url), "relevance");

    // Сюжет попадает в список, если хоть одно размещение прошло фильтр; внутри — все размещения.
    // Одиночки отдаём как сюжет из одного размещения.
    const groups: S["ResultGroup"][] = [];
    const seen = new Set<string>();
    for (const r of matched) {
      const key = r.group_id ?? `single-${r.id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const items = r.group_id
        ? visible.filter((x) => x.group_id === r.group_id && (includeExcluded || !x.excluded))
        : [r];
      const dates = items.map((x) => x.published_at).filter((d): d is string => !!d).sort();
      groups.push({
        group_id: key,
        title: items[0].title,
        size: items.length,
        platforms: [...new Set(items.map((x) => x.platform))],
        earliest_published_at: dates[0] ?? null,
        items,
      });
    }
    return HttpResponse.json(page(groups, url));
  }),

  http.post(`${API}/searches/:searchId/results/exclusion`, async ({ request, params }) => {
    await delay(200);
    const rec = getSearch(params.searchId as string);
    if (!rec) return notFound();
    const body = ((await request.json().catch(() => ({}))) ?? {}) as Partial<S["ExclusionIn"]>;
    const ids = (body.result_ids ?? []).filter((id) => db.hasResult(rec, id));
    if (!body.result_ids?.length) {
      return apiError(422, "VALIDATION_ERROR", "Не выбраны публикации", [{ field: "result_ids", message: "Минимум одна" }]);
    }
    if (!ids.length) return apiError(404, "RESULT_NOT_FOUND", "Публикация не найдена");
    db.setExcluded(rec, ids, body.excluded ?? true);
    return HttpResponse.json({ counts: db.snapshot(rec).search.counts });
  }),

  http.get(`${API}/searches/:searchId/export`, async ({ request, params }) => {
    await delay(500);
    const rec = getSearch(params.searchId as string);
    if (!rec) return notFound();
    const format = new URL(request.url).searchParams.get("format") === "docx" ? "docx" : "xlsx";
    const type =
      format === "xlsx"
        ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        : "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    const date = new Date().toISOString().slice(0, 10);
    return new HttpResponse(new Blob(["mock"]), {
      headers: { "Content-Type": type, "Content-Disposition": `attachment; filename="podborka_${date}.${format}"` },
    });
  }),
];

// ── вспомогательное ──

function validateSearch(b: Partial<S["SearchCreateIn"]>) {
  const d: { field: string; message: string }[] = [];
  const ymd = /^\d{4}-\d{2}-\d{2}$/;
  if (!b.query || b.query.trim().length < 3) d.push({ field: "query", message: "Введите хотя бы 3 символа" });
  else if (b.query.length > 20000) d.push({ field: "query", message: "Не больше 20000 символов" });
  if (!b.period_from || !ymd.test(b.period_from)) d.push({ field: "period_from", message: "Укажите дату начала" });
  if (!b.period_to || !ymd.test(b.period_to)) d.push({ field: "period_to", message: "Укажите дату окончания" });
  if (b.period_from && b.period_to && b.period_from > b.period_to) {
    d.push({ field: "period_to", message: "Дата окончания раньше даты начала" });
  }
  if (b.mode !== "selected" && b.mode !== "global") d.push({ field: "mode", message: "Выберите, где искать" });
  if (!b.platforms?.length) d.push({ field: "platforms", message: "Выберите хотя бы одну площадку" });
  if (b.mode === "selected" && !b.source_ids?.length) d.push({ field: "source_ids", message: "Выберите хотя бы один источник" });
  return d;
}

const URL_PATTERNS: { platform: S["Platform"]; re: RegExp }[] = [
  { platform: "vk", re: /^(?:https?:\/\/)?(?:m\.)?vk\.(?:com|ru)\/([\w.]+)/i },
  { platform: "ok", re: /^(?:https?:\/\/)?(?:m\.)?ok\.ru\/(?:group\/)?([\w.]+)/i },
  { platform: "max", re: /^(?:https?:\/\/)?max\.ru\/([\w.]+)/i },
];

function resolve(raw: string): S["SourcePreview"] | Response {
  const url = raw.trim();
  if (/bad/i.test(url)) return apiError(422, "UNSUPPORTED_URL", "Это не похоже на ссылку на группу VK, OK или канал MAX");
  if (/notfound/i.test(url)) return apiError(404, "SOURCE_NOT_FOUND", "Такой группы или канала не нашлось — проверьте ссылку");
  if (/private/i.test(url)) return apiError(409, "SOURCE_PRIVATE", "Группа закрыта — публикации недоступны");
  if (/down/i.test(url)) return apiError(503, "PLATFORM_UNAVAILABLE", "ВКонтакте сейчас недоступна, попробуйте позже");

  const match = URL_PATTERNS.map((p) => ({ p, m: url.match(p.re) })).find((x) => x.m);
  if (!match?.m) return apiError(422, "UNSUPPORTED_URL", "Это не похоже на ссылку на группу VK, OK или канал MAX");

  const slug = match.m[1];
  const normalized = `https://${{ vk: "vk.com", ok: "ok.ru/group", max: "max.ru", news: "" }[match.p.platform]}/${slug}`;
  const existing = /exists/i.test(url)
    ? db.sources[0]
    : db.sources.find((s) => s.url.toLowerCase() === normalized.toLowerCase() || s.url.toLowerCase() === url.toLowerCase());
  return {
    platform: match.p.platform,
    external_id: slug,
    url: existing?.url ?? normalized,
    name: existing?.name ?? `Сообщество ${slug}`,
    city: existing?.city ?? "Красноярск",
    members_count: slug.length % 3 === 0 ? null : 1000 + slug.length * 1371,
    existing_source_id: existing?.id ?? null,
  };
}
