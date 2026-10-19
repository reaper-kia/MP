// Состояние фильтров подборки живёт в URL (?relevance=direct&platform=vk&sort=date_desc&group=1),
// чтобы «назад» и выгрузка (FE-07) видели ровно то, что на экране.
import { useRef } from "react";
import { useSearchParams } from "react-router";

import type { S } from "../../api/client";

export type Tab = "all" | S["Relevance"];
export type Sort = "relevance" | "date_desc" | "date_asc";

export interface ResultFilters {
  tab: Tab;
  platform: S["Platform"][];
  target_id: string[];
  unknownDateOnly: boolean;
  include_excluded: boolean;
  sort: Sort;
  group: boolean;
}

const TABS: Tab[] = ["all", "direct", "indirect", "disputed", "rejected"];
const SORTS: Sort[] = ["relevance", "date_desc", "date_asc"];

function parse(params: URLSearchParams): ResultFilters {
  const rel = params.get("relevance") as Tab | null;
  const sort = params.get("sort") as Sort | null;
  return {
    tab: rel && TABS.includes(rel) ? rel : "all",
    platform: params.getAll("platform") as S["Platform"][],
    target_id: params.getAll("target_id"),
    unknownDateOnly: params.get("date_status") === "unknown",
    include_excluded: params.get("include_excluded") === "true",
    sort: sort && SORTS.includes(sort) ? sort : "relevance",
    group: params.get("group") === "1",
  };
}

export function useResultFilters() {
  const [params, setParams] = useSearchParams();
  // Последние параметры, включая ещё не отрисованные: два быстрых клика подряд не должны затирать друг друга
  const latest = useRef(params);
  latest.current = params;
  const filters = parse(params);

  function update(patch: Partial<ResultFilters>) {
    const f = { ...parse(latest.current), ...patch };
    const next = new URLSearchParams();
    if (f.tab !== "all") next.set("relevance", f.tab);
    f.platform.forEach((p) => next.append("platform", p));
    f.target_id.forEach((t) => next.append("target_id", t));
    if (f.unknownDateOnly) next.set("date_status", "unknown");
    if (f.include_excluded) next.set("include_excluded", "true");
    if (f.sort !== "relevance") next.set("sort", f.sort);
    if (f.group) next.set("group", "1");
    latest.current = next;
    setParams(next, { replace: true });
  }

  return { filters, update };
}

/** Параметры для GET /results (и /export в FE-07). Вкладка «Все» — relevance не передаём. */
export function listQuery(f: ResultFilters) {
  return {
    relevance: f.tab === "all" ? undefined : [f.tab],
    platform: f.platform.length ? f.platform : undefined,
    target_id: f.target_id.length ? f.target_id : undefined,
    date_status: f.unknownDateOnly ? (["unknown"] as S["DateStatus"][]) : undefined,
    include_excluded: f.include_excluded || undefined,
    sort: f.sort,
  };
}

/**
 * Параметры для GET /export — ровно то, что на экране, но без include_excluded:
 * исключённые в файл не попадают никогда. В режиме сюжетов экран фильтрует только по relevance и platform.
 */
export function exportQuery(f: ResultFilters, grouped: boolean) {
  if (grouped) {
    const { relevance, platform } = groupsQuery(f);
    return { relevance, platform };
  }
  const { relevance, platform, target_id, date_status, sort } = listQuery(f);
  return { relevance, platform, target_id, date_status, sort };
}

/** /groups не знает target_id, date_status и sort. */
export function groupsQuery(f: ResultFilters) {
  const { relevance, platform, include_excluded } = listQuery(f);
  return { relevance, platform, include_excluded };
}
