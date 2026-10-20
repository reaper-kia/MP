// Сценарии поиска для MSW: по тексту запроса выбираем, какие цели будут и что найдётся.
// Всё детерминировано от seed, поэтому после перезагрузки страницы подборка та же.
import type { S } from "../../api/client";
import { dayjs, TZ } from "../../lib/dates";
import { GLOBAL_COMMUNITIES, PLATFORM_NAME, PLATFORMS, SOURCES } from "./catalog";
import { REJECTED_TEMPLATES, SECURITY_ITEMS, type FixtureItem } from "./texts";

export type Scenario = "security" | "news_text" | "empty" | "error" | "default";

export function detectScenario(query: string): Scenario {
  const q = query.toLowerCase();
  if (q.includes("ошибка")) return "error";
  if (q.includes("пусто")) return "empty";
  if (q.includes("безопасность")) return "security";
  if (query.length > 300) return "news_text";
  return "default";
}

export type TargetInfo = Pick<S["SearchTarget"], "id" | "kind" | "platform" | "source_id" | "name" | "url">;

export interface TargetPlan {
  info: TargetInfo;
  final: { status: "done" | "empty" | "failed"; fetched: number; error: S["ErrorInfo"] | null };
}

// ── анализ запроса ──

export function analyzeQuery(query: string): S["QueryAnalysis"] {
  const q = query.trim();
  if (q.length > 300) {
    const first = q.split(/(?<=[.!?])\s/)[0] ?? q;
    return {
      query_type: "news_text",
      summary: `Текст новости: «${cut(first, 90)}» — ищем её размещения`,
      search_queries: [cut(first, 120)],
      needs_clarification: false,
      clarification_hint: null,
    };
  }
  if (q.toLowerCase().includes("безопасность")) {
    return {
      query_type: "topic",
      summary: "Тема: безопасность дорожного движения (ДТП, ГИБДД, пешеходы) в Красноярском крае",
      search_queries: ["безопасность дорожного движения", "ДТП Красноярск", "ГИБДД рейд", "пешеходный переход"],
      needs_clarification: false,
      clarification_hint: null,
    };
  }
  const words = q.split(/\s+/).filter(Boolean);
  const short = words.length <= 1 && q.length < 12;
  const isEvent = /\d|авари|пожар|открыт|прошл|состоял|задерж/i.test(q);
  const isPerson = words.length >= 2 && words.length <= 3 && words.every((w) => /^[А-ЯЁ][а-яё-]+$/.test(w));
  const type: S["QueryType"] = isPerson ? "person" : isEvent ? "event" : "topic";
  return {
    query_type: type,
    summary: `${{ topic: "Тема", event: "Событие", person: "Человек", news_text: "Текст новости" }[type]}: ${cut(q, 120)}`,
    search_queries: [q],
    needs_clarification: short,
    clarification_hint: short ? "Запрос короткий — уточните, что именно ищете: событие, место или человека" : null,
  };
}

// ── цели ──

export function planTargets(scenario: Scenario, params: S["SearchParams"], searchId: string): TargetPlan[] {
  const tid = (i: number) => `${searchId.slice(0, 8)}-t${i}`;

  if (scenario === "security") {
    const vkSrc = SOURCES[0];
    return [
      {
        info: { id: tid(0), kind: "source", platform: "vk", source_id: vkSrc.id, name: vkSrc.name, url: vkSrc.url },
        final: { status: "done", fetched: 214, error: null },
      },
      {
        info: { id: tid(1), kind: "platform_search", platform: "vk", source_id: null, name: "Поиск по всему VK", url: null },
        final: { status: "done", fetched: 263, error: null },
      },
      {
        info: { id: tid(2), kind: "platform_search", platform: "ok", source_id: null, name: "Поиск по всему OK", url: null },
        final: {
          status: "failed",
          fetched: 0,
          error: { code: "TIMEOUT", message: "Одноклассники не ответили за 30 секунд" },
        },
      },
      {
        info: { id: tid(3), kind: "source", platform: "max", source_id: SOURCES[9].id, name: SOURCES[9].name, url: SOURCES[9].url },
        final: { status: "empty", fetched: 0, error: null },
      },
    ];
  }

  const infos = targetsFromParams(params).map((t, i) => ({ ...t, id: tid(i) }));
  return infos.map((info, i): TargetPlan => {
    if (scenario === "error") {
      return {
        info,
        final: {
          status: "failed",
          fetched: 0,
          error: { code: "PLATFORM_UNAVAILABLE", message: `${PLATFORM_NAME[info.platform]} сейчас недоступна, попробуйте позже` },
        },
      };
    }
    // как настоящий бэкенд: цель «поиск по площадке» создаётся и там, где площадка его не умеет, и падает
    if (info.kind === "platform_search" && !PLATFORMS.find((p) => p.code === info.platform)?.global_mode) {
      return {
        info,
        final: {
          status: "failed",
          fetched: 0,
          error: { code: "PLATFORM_UNAVAILABLE", message: `${PLATFORM_NAME[info.platform]}: поиск по всей площадке не поддерживается` },
        },
      };
    }
    if (scenario === "empty") {
      return { info, final: i % 2 ? { status: "empty", fetched: 0, error: null } : { status: "done", fetched: 30 + i * 7, error: null } };
    }
    return { info, final: { status: "done", fetched: 40 + i * 13, error: null } };
  });
}

function targetsFromParams(params: S["SearchParams"]): Omit<TargetInfo, "id">[] {
  const fromSource = (s: S["Source"]): Omit<TargetInfo, "id"> => ({
    kind: "source",
    platform: s.platform,
    source_id: s.id,
    name: s.name,
    url: s.url,
  });
  const out: Omit<TargetInfo, "id">[] = [];

  if (params.mode === "selected") {
    let picked = SOURCES.filter((s) => params.source_ids.includes(s.id) && params.platforms.includes(s.platform));
    // id не из нашего каталога (например, пришли из Prism) — берём активные источники выбранных площадок
    if (picked.length === 0) picked = SOURCES.filter((s) => s.is_active && params.platforms.includes(s.platform));
    out.push(...picked.map(fromSource));
  } else {
    for (const p of params.platforms) {
      const info = PLATFORMS.find((x) => x.code === p);
      // как бэкенд: поиск по площадке — для каждой площадки (без global_mode он упадёт),
      // плюс активные источники каталога там, где поиска по всей площадке нет
      out.push({ kind: "platform_search", platform: p, source_id: null, name: `Поиск по всему ${p.toUpperCase()}`, url: null });
      if (!info?.global_mode) out.push(...SOURCES.filter((s) => s.platform === p && s.is_active).map(fromSource));
    }
  }
  if (out.length === 0) {
    const p = params.platforms[0] ?? "vk";
    out.push({ kind: "platform_search", platform: p, source_id: null, name: `Поиск по всему ${p.toUpperCase()}`, url: null });
  }
  return out.slice(0, 8);
}

// ── результаты ──

interface Ctx {
  searchId: string;
  params: S["SearchParams"];
  targets: TargetPlan[];
  rnd: () => number;
}

export function buildResults(scenario: Scenario, ctx: Ctx): S["Result"][] {
  switch (scenario) {
    case "security":
      return [...securityResults(ctx), ...rejectedResults(ctx, 436)];
    case "news_text":
      return newsTextResults(ctx);
    case "default":
      return genericResults(ctx, ctx.targets.filter((t) => t.final.status === "done"), 10, "r");
    default:
      return [];
  }
}

/** Что «досыпается» после успешного повтора упавшей цели. */
export function retryResults(ctx: Ctx, target: TargetPlan): S["Result"][] {
  return genericResults(ctx, [target], 2, `${target.info.id}-retry`);
}

function securityResults(ctx: Ctx): S["Result"][] {
  const [tSrc, tGlobal] = ctx.targets;
  const communities = GLOBAL_COMMUNITIES.vk;
  return SECURITY_ITEMS.map((item, i) => {
    // чётные — из источника каталога, нечётные — глобальный поиск по VK
    const fromSource = i % 2 === 0;
    const target = fromSource ? tSrc : tGlobal;
    const comm = communities[i % communities.length];
    const source = fromSource
      ? { id: SOURCES[0].id, name: SOURCES[0].name, url: SOURCES[0].url, is_regional: true }
      : { id: null, name: comm.name, url: comm.url, is_regional: true };
    return makeResult(ctx, `r${i + 1}`, item, target, source);
  });
}

function rejectedResults(ctx: Ctx, n: number): S["Result"][] {
  const done = ctx.targets.filter((t) => t.final.status === "done");
  return Array.from({ length: n }, (_, i) => {
    const tpl = REJECTED_TEMPLATES[i % REJECTED_TEMPLATES.length];
    const target = done[i % done.length];
    const comm = GLOBAL_COMMUNITIES[target.info.platform][i % GLOBAL_COMMUNITIES[target.info.platform].length];
    const item: FixtureItem = { title: tpl.title, text: tpl.text, hl: [], rel: "disputed", why: tpl.why, sentiment: null };
    const r = makeResult(ctx, `x${i + 1}`, item, target, { id: null, name: comm.name, url: comm.url, is_regional: true });
    return { ...r, relevance: "rejected", score: round(0.05 + ctx.rnd() * 0.2) };
  });
}

function newsTextResults(ctx: Ctx): S["Result"][] {
  const q = ctx.params.query.trim();
  const sentences = q.split(/(?<=[.!?])\s+/);
  const first = sentences[0] ?? q;
  const done = ctx.targets.filter((t) => t.final.status === "done");
  const t = (i: number) => done[i % done.length];
  const key = first.slice(0, 60);
  const variants: FixtureItem[] = [
    {
      group: "g-news",
      title: cut(first, 100),
      text: cut(q, 400),
      hl: [key],
      rel: "direct",
      why: "Копия исходного текста.",
      sentiment: "neutral",
    },
    {
      group: "g-news",
      title: cut(first, 80),
      text: `${first} Подробности — по ссылке.`,
      hl: [key],
      rel: "direct",
      why: "Сокращённая версия исходного текста.",
      sentiment: "neutral",
    },
    {
      group: "g-news",
      title: "Пересказ новости",
      text: `Как сообщают местные СМИ, ${lowerFirst(cut(first, 160))} Редакция следит за развитием событий.`,
      hl: [lowerFirst(first).slice(0, 40)],
      rel: "direct",
      why: "Пересказ исходной новости своими словами.",
      sentiment: "neutral",
      postStart: true,
    },
  ];
  const out = variants.map((v, i) => {
    const comm = GLOBAL_COMMUNITIES[t(i).info.platform];
    return makeResult(ctx, `r${i + 1}`, v, t(i), { id: null, name: comm[i % comm.length].name, url: comm[i % comm.length].url, is_regional: true });
  });
  const other = makeResult(
    ctx,
    "x1",
    {
      title: "Похожая новость о другом событии",
      text: "Похожий сюжет, но речь о событии прошлого года в другом районе.",
      hl: [],
      rel: "disputed",
      why: "Другое событие: совпадают слова, но не место и дата.",
      sentiment: "neutral",
    },
    t(0),
    { id: null, name: "Сибирь сегодня", url: "https://max.ru/sibir_today", is_regional: false },
  );
  return [...out, { ...other, relevance: "rejected", score: 0.21 }];
}

const GENERIC_TITLES = [
  "В Красноярске обсудили: {q}",
  "{Q} — что известно на сегодня",
  "Жители края рассказали о том, что думают про «{q}»",
  "Депутаты горсовета вернулись к вопросу «{q}»",
  "{Q}: комментарий администрации",
  "Что изменится: {q}",
  "В Ачинске тоже заговорили про «{q}»",
  "{Q}. Фоторепортаж",
  "Эксперт: {q} — не главная проблема",
  "Опрос читателей: {q}",
];

function genericResults(ctx: Ctx, targets: TargetPlan[], n: number, prefix: string): S["Result"][] {
  if (targets.length === 0) return [];
  const q = cut(ctx.params.query.trim(), 60);
  const rels: FixtureItem["rel"][] = ["direct", "direct", "indirect", "direct", "disputed", "direct", "indirect", "direct", "indirect", "direct"];
  return Array.from({ length: n }, (_, i) => {
    const target = targets[i % targets.length];
    const title = GENERIC_TITLES[(i + prefix.length) % GENERIC_TITLES.length].replace("{q}", q).replace("{Q}", upperFirst(q));
    const item: FixtureItem = {
      title,
      text: `Сегодня снова говорили о теме «${q}». Мнения разделились: часть жителей поддерживает изменения, часть считает, что нужно подождать.`,
      hl: [q],
      rel: rels[i % rels.length],
      why: "Публикация упоминает запрос и рассказывает о нём в контексте края.",
      sentiment: (["neutral", "positive", "negative", null] as const)[i % 4],
      group: prefix === "r" && i < 2 ? "g-1" : undefined,
      evidence: i === 6 ? "Упоминается Ачинск" : undefined,
    };
    const source =
      target.info.kind === "source"
        ? { id: target.info.source_id, name: target.info.name, url: target.info.url ?? "", is_regional: true }
        : (() => {
            const c = GLOBAL_COMMUNITIES[target.info.platform][i % GLOBAL_COMMUNITIES[target.info.platform].length];
            return { id: null, name: c.name, url: c.url, is_regional: true };
          })();
    return makeResult(ctx, `${prefix}${i + 1}`, item, target, source);
  });
}

function makeResult(ctx: Ctx, key: string, item: FixtureItem, target: TargetPlan, source: S["Result"]["source"]): S["Result"] {
  const id = `${ctx.searchId.slice(0, 8)}-${key}`;
  const published = item.noDate ? null : randomDate(ctx);
  const score =
    item.rel === "direct" ? 0.8 + ctx.rnd() * 0.17 : item.rel === "indirect" ? 0.55 + ctx.rnd() * 0.2 : 0.4 + ctx.rnd() * 0.14;
  const views = ctx.rnd() < 0.15 ? null : Math.round(200 + ctx.rnd() * 9000);
  return {
    id,
    publication_id: `p-${id}`,
    platform: target.info.platform,
    source,
    url: `${source.url.replace(/\/$/, "")}?w=wall${Math.round(ctx.rnd() * 1e6)}`,
    title: item.title,
    title_source: item.postStart ? "post_start" : "title",
    excerpt: item.text,
    excerpt_parts: highlight(item.text, item.hl),
    published_at: published,
    date_status: published ? "in_period" : "unknown",
    relevance: item.rel,
    score: round(score),
    explanation: item.why,
    region: { by_source: source.is_regional, by_content: !!item.evidence, evidence: item.evidence ?? null },
    sentiment: item.sentiment,
    group_id: item.group ? `${ctx.searchId.slice(0, 8)}-${item.group}` : null,
    group_size: 1, // пересчитывается в db после сборки
    metrics: {
      views,
      likes: views === null ? null : Math.round(views * 0.01 * (1 + ctx.rnd() * 3)),
      reposts: ctx.rnd() < 0.3 ? null : Math.round(ctx.rnd() * 20),
      comments: ctx.rnd() < 0.3 ? null : Math.round(ctx.rnd() * 40),
    },
    excluded: false,
    found_by_target_id: target.info.id,
  };
}

// ── утилиты ──

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function randomDate(ctx: Ctx): string {
  const from = dayjs.tz(ctx.params.period_from, TZ).startOf("day").valueOf();
  const to = Math.min(dayjs.tz(ctx.params.period_to, TZ).endOf("day").valueOf(), Date.now());
  const t = from + ctx.rnd() * Math.max(0, to - from);
  return new Date(Math.floor(t / 60000) * 60000).toISOString().replace(".000Z", "Z");
}

function highlight(text: string, words: string[]): S["ExcerptPart"][] {
  const ws = words.filter(Boolean).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (ws.length === 0) return [{ text, highlight: false }];
  const re = new RegExp(`(${ws.join("|")})`, "gi");
  return text
    .split(re)
    .filter((p) => p !== "")
    .map((p) => ({ text: p, highlight: ws.some((w) => new RegExp(`^${w}$`, "i").test(p)) }));
}

function cut(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s;
}
function round(x: number): number {
  return Math.round(x * 100) / 100;
}
function upperFirst(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
function lowerFirst(s: string): string {
  return s.charAt(0).toLowerCase() + s.slice(1);
}
