// In-memory «бэкенд» для MSW. Состояние поиска считается от времени с момента POST,
// поэтому опрос GET /searches/:id видит, как поиск идёт. Записи поисков и источники
// дублируются в localStorage (в try/catch), чтобы /search/:id переживал перезагрузку.
// Подборку не храним: она детерминированно пересобирается из seed.
import type { S } from "../api/client";
import { SOURCES } from "./fixtures/catalog";
import {
  analyzeQuery,
  buildResults,
  detectScenario,
  mulberry32,
  planTargets,
  retryResults,
  type Scenario,
  type TargetPlan,
} from "./fixtures/scenarios";

// Таймлайн поиска, мс от создания
const T_ANALYZE = 1000;
const QUEUE_DEMO = 10000;
const T_COLLECT = 2000;
const COLLECT_SPAN = 6000;
const T_SCORE = 8000;
const T_GROUP = 9000;
const T_DONE = 10000;
// Повтор цели: pending → running → done
const RETRY_RUNNING = 1000;
const RETRY_DONE = 3000;

export interface SearchRecord {
  id: string;
  seed: number;
  createdAt: number;
  scenario: Scenario;
  params: S["SearchParams"];
  analysis: S["QueryAnalysis"];
  targets: TargetPlan[];
  retryAt: Record<string, number>; // target_id → когда нажали «Повторить»
  cancelledAt: number | null;
  excluded: string[];
  warnings: string[];
}

export const searches = new Map<string, SearchRecord>();
export const results = new Map<string, S["Result"][]>(); // кэш подборки по search_id
export let sources: S["Source"][] = [...SOURCES];

const STORAGE_KEY = "mp-mocks-v1";

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ searches: [...searches.values()], sources }));
  } catch {
    // приватный режим / нет места — живём в памяти
  }
}

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const data = JSON.parse(raw) as { searches: SearchRecord[]; sources: S["Source"][] };
    data.searches.forEach((r) => searches.set(r.id, r));
    sources = data.sources;
    return true;
  } catch {
    return false;
  }
}

export function resetDb() {
  searches.clear();
  results.clear();
  sources = [...SOURCES];
  seedHistory();
  save();
}

// ── поиски ──

export function createSearch(input: S["SearchCreateIn"], createdAt = Date.now()): SearchRecord {
  const id = crypto.randomUUID();
  const scenario = detectScenario(input.query);
  const analysis = analyzeQuery(input.query);
  const params: S["SearchParams"] = {
    query: input.query,
    query_type: analysis.query_type,
    period_from: input.period_from,
    period_to: input.period_to,
    mode: input.mode,
    platforms: input.platforms,
    source_ids: input.source_ids,
  };
  const rec: SearchRecord = {
    id,
    seed: Math.floor(Math.random() * 2 ** 31),
    // «очередь» в запросе — поиск 10 с ждёт в очереди (B2-15), чтобы показать это состояние
    createdAt: input.query.toLowerCase().includes("очередь") ? createdAt + QUEUE_DEMO : createdAt,
    scenario,
    params,
    analysis,
    targets: planTargets(scenario, params, id),
    retryAt: {},
    cancelledAt: null,
    excluded: [],
    warnings: scenario === "security" ? ["Одноклассники: глобальный поиск идёт через Яндекс — покрытие неполное"] : [],
  };
  searches.set(id, rec);
  save();
  return rec;
}

function allResults(rec: SearchRecord): S["Result"][] {
  let list = results.get(rec.id);
  if (!list) {
    const ctx = { searchId: rec.id, params: rec.params, targets: rec.targets, rnd: mulberry32(rec.seed) };
    list = buildResults(rec.scenario, ctx);
    for (const t of rec.targets) {
      if (rec.retryAt[t.info.id] !== undefined) list.push(...retryResults({ ...ctx, rnd: mulberry32(rec.seed + 1) }, t));
    }
    // размер сюжета — по всем размещениям группы
    const sizes = new Map<string, number>();
    list.forEach((r) => r.group_id && sizes.set(r.group_id, (sizes.get(r.group_id) ?? 0) + 1));
    list.forEach((r) => (r.group_size = r.group_id ? (sizes.get(r.group_id) ?? 1) : 1));
    results.set(rec.id, list);
  }
  const excluded = new Set(rec.excluded);
  list.forEach((r) => (r.excluded = excluded.has(r.id)));
  return list;
}

function targetState(rec: SearchRecord, plan: TargetPlan, index: number, now: number): S["SearchTarget"] {
  const base = { ...plan.info, fetched: 0, matched: 0, error: null, attempts: 1, finished_at: null };
  const iso = (ms: number) => new Date(ms).toISOString();

  const retryAt = rec.retryAt[plan.info.id];
  if (retryAt !== undefined) {
    const r = now - retryAt;
    if (r < RETRY_RUNNING) return { ...base, status: "pending", attempts: 2 };
    if (r < RETRY_DONE) return { ...base, status: "running", attempts: 2 };
    return { ...base, status: "done", fetched: plan.final.fetched || 18, attempts: 2, finished_at: iso(retryAt + RETRY_DONE) };
  }

  const n = rec.targets.length;
  const step = Math.min(1500, COLLECT_SPAN / Math.max(n, 1));
  const start = rec.createdAt + T_COLLECT + index * step;
  const end = start + step;
  const stopAt = rec.cancelledAt ?? Infinity;

  if (now >= end && end <= stopAt) {
    return { ...base, status: plan.final.status, fetched: plan.final.fetched, error: plan.final.error, finished_at: iso(end) };
  }
  if (now >= stopAt) return { ...base, status: "skipped" };
  if (now >= start) return { ...base, status: "running", fetched: Math.round(plan.final.fetched * ((now - start) / step)) };
  return { ...base, status: "pending" };
}

const isFinished = (t: S["SearchTarget"]) => ["done", "empty", "failed", "skipped"].includes(t.status);

/** Срез поиска на текущий момент + видимые результаты (от уже обработанных целей). */
export function snapshot(rec: SearchRecord, now = Date.now()) {
  const targets = rec.targets.map((p, i) => targetState(rec, p, i, now));
  const doneTargets = new Set(targets.filter((t) => t.status === "done").map((t) => t.id));
  const visible = allResults(rec).filter((r) => doneTargets.has(r.found_by_target_id));

  for (const t of targets) {
    t.matched = visible.filter((r) => r.found_by_target_id === t.id && r.relevance !== "rejected").length;
  }

  const e = now - rec.createdAt;
  const finished = targets.filter(isFinished).length;
  const retrying = Object.values(rec.retryAt).some((at) => now - at < RETRY_DONE);

  let status: S["SearchStatus"];
  let stage: S["SearchStage"];
  let percent: number;
  if (rec.cancelledAt !== null && now >= rec.cancelledAt) {
    [status, stage, percent] = ["cancelled", "done", 100];
  } else if (retrying) {
    [status, stage, percent] = ["running", "collecting", Math.round(10 + (80 * finished) / targets.length)];
  } else if (e < T_ANALYZE) {
    [status, stage, percent] = ["queued", "queued", 0];
  } else if (e < T_COLLECT) {
    [status, stage, percent] = ["running", "analyzing_query", 5];
  } else if (e < T_SCORE) {
    [status, stage, percent] = ["running", "collecting", Math.round(10 + (70 * finished) / targets.length)];
  } else if (e < T_GROUP) {
    [status, stage, percent] = ["running", "scoring", 85];
  } else if (e < T_DONE) {
    [status, stage, percent] = ["running", "grouping", 95];
  } else {
    const failed = targets.filter((t) => t.status === "failed").length;
    status = failed === targets.length ? "failed" : failed > 0 ? "partial" : "completed";
    [stage, percent] = ["done", 100];
  }

  const final = ["completed", "partial", "failed", "cancelled"].includes(status);
  const lastRetry = Math.max(0, ...Object.values(rec.retryAt));
  const search: S["Search"] = {
    id: rec.id,
    status,
    stage,
    progress: { targets_total: targets.length, targets_finished: finished, percent },
    params: { ...rec.params, query_type: e >= T_ANALYZE ? rec.params.query_type : null },
    query_analysis: e >= T_ANALYZE ? rec.analysis : null,
    targets,
    counts: countsOf(visible),
    warnings: e >= T_COLLECT ? rec.warnings : [],
    created_at: new Date(rec.createdAt).toISOString(),
    started_at: e >= T_ANALYZE ? new Date(rec.createdAt + T_ANALYZE).toISOString() : null,
    finished_at: final
      ? new Date(rec.cancelledAt ?? Math.max(rec.createdAt + T_DONE, lastRetry ? lastRetry + RETRY_DONE : 0)).toISOString()
      : null,
    cache: null,
  };
  return { search, visible, final };
}

export function countsOf(list: S["Result"][]): S["SearchCounts"] {
  const inSet = list.filter((r) => r.relevance !== "rejected");
  const kept = inSet.filter((r) => !r.excluded);
  const by = (rel: S["Relevance"]) => kept.filter((r) => r.relevance === rel).length;
  return {
    total: kept.length,
    direct: by("direct"),
    indirect: by("indirect"),
    disputed: by("disputed"),
    rejected: list.filter((r) => r.relevance === "rejected").length,
    excluded: inSet.filter((r) => r.excluded).length,
    unknown_date: kept.filter((r) => r.date_status === "unknown").length,
    groups: new Set(kept.map((r) => r.group_id).filter(Boolean)).size,
  };
}

export function retry(rec: SearchRecord, targetIds: string[] | undefined, now = Date.now()) {
  const { search } = snapshot(rec, now);
  const ids = targetIds?.length ? targetIds : search.targets.filter((t) => t.status === "failed").map((t) => t.id);
  ids.forEach((id) => (rec.retryAt[id] = now));
  results.delete(rec.id); // пересобрать с «досыпанными» результатами
  save();
}

export function cancel(rec: SearchRecord, now = Date.now()) {
  rec.cancelledAt = now;
  save();
}

export function setExcluded(rec: SearchRecord, ids: string[], excluded: boolean) {
  const set = new Set(rec.excluded);
  ids.forEach((id) => (excluded ? set.add(id) : set.delete(id)));
  rec.excluded = [...set];
  save();
}

export function hasResult(rec: SearchRecord, id: string) {
  return allResults(rec).some((r) => r.id === id);
}

// ── источники ──

export function saveSources(next: S["Source"][]) {
  sources = next;
  save();
}

// ── начальное состояние: пара поисков в истории ──

function seedHistory() {
  const day = 24 * 3600 * 1000;
  const now = Date.now();
  createSearch(
    {
      query: "Безопасность дорожного движения в Красноярском крае",
      period_from: ymd(now - 8 * day),
      period_to: ymd(now - 2 * day),
      mode: "global",
      platforms: ["vk", "ok", "max"],
      source_ids: [],
    },
    now - 2 * day,
  );
  createSearch(
    {
      query: "Паводок на Енисее",
      period_from: ymd(now - 7 * day),
      period_to: ymd(now - day),
      mode: "selected",
      platforms: ["vk", "max"],
      source_ids: [SOURCES[0].id, SOURCES[2].id, SOURCES[9].id],
    },
    now - day,
  );
}

function ymd(ms: number) {
  return new Date(ms + 7 * 3600 * 1000).toISOString().slice(0, 10); // Красноярск, UTC+7
}

if (!load()) resetDb();
