import { Button, Center, Skeleton, Switch, Tabs } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type { S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { PlatformLogo } from "../../components/PlatformLogo";
import { fmtNumber, publications } from "../../lib/format";
import { PLATFORM_NAME } from "../../lib/platforms";
import { useConnectionNotice } from "../../lib/useConnectionNotice";
import { isFinal } from "../search/status";
import { ExportBar } from "./ExportBar";
import { useResultFilters, type Sort, type Tab } from "./filters";
import { GroupCard } from "./GroupCard";
import { ResultCard } from "./ResultCard";
import classes from "./ResultsView.module.css";
import { useExclusion, useGroupList, useResultList } from "./useResults";

// Сортировки макета v2 — те, что умеет GET /results (sort); «Популярное» и «Официальное» API не поддерживает
const SORT_OPTIONS: { value: Sort; label: string }[] = [
  { value: "relevance", label: "По релевантности" },
  { value: "date_desc", label: "Новое" },
  { value: "date_asc", label: "Старое" },
];

const cut = (s: string, n: number) => {
  const one = s.replace(/\s+/g, " ").trim();
  return one.length > n ? `${one.slice(0, n - 1).trimEnd()}…` : one;
};

export function ResultsView({ search }: { search: S["Search"] }) {
  const { filters: f, update } = useResultFilters();
  const running = !isFinal(search.status);
  const c = search.counts;
  const grouped = f.group && f.tab !== "rejected";

  const list = useResultList(search.id, f, running, !grouped);
  const groups = useGroupList(search.id, f, running, grouped);
  const active = grouped ? groups : list;
  useConnectionNotice(active);

  // Поиск завершился (или повтор добавил публикации) — перечитать списки один раз: опрос раз в 3 с
  // останавливается на финальном статусе, и последний ответ мог прийти раньше, чем бэкенд дописал подборку.
  const queryClient = useQueryClient();
  useEffect(() => {
    queryClient.invalidateQueries({ queryKey: ["results", search.id] });
  }, [queryClient, search.id, search.status, c.total, c.rejected]);

  const exclusion = useExclusion(search.id);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [lastExcluded, setLastExcluded] = useState<string[]>([]);
  // Выделение относится к тому, что на экране: сменили фильтры — сбрасываем
  const filtersKey = JSON.stringify(f);
  useEffect(() => setSelected(new Set()), [filtersKey]);

  const select = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const exclude = (ids: string[], excluded: boolean) => {
    exclusion.mutate({ ids, excluded });
    setLastExcluded(excluded ? ids : []);
    setSelected((prev) => new Set([...prev].filter((id) => !ids.includes(id))));
  };

  const togglePlatform = (p: S["Platform"]) =>
    update({ platform: f.platform.includes(p) ? f.platform.filter((x) => x !== p) : [...f.platform, p] });

  const pages = active.data?.pages ?? [];
  const total = pages[0]?.total ?? 0;

  return (
    <section className={classes.section}>
      <div className={classes.head}>
        <div>
          <h2 className={classes.heading}>
            Результаты <span className={classes.headingCount}>{fmtNumber(c.total)}</span>
          </h2>
          <p className={classes.sub}>По запросу «{cut(search.params.query, 72)}»</p>
        </div>
        <ExportBar search={search} filters={f} grouped={grouped} />
      </div>

      <Tabs
        value={f.tab}
        onChange={(v) => update({ tab: (v ?? "all") as Tab })}
        classNames={{ list: classes.tabsList, tab: classes.tab }}
      >
        <Tabs.List>
          <Tabs.Tab value="all">
            Все <span className={classes.tabCount}>{fmtNumber(c.total)}</span>
          </Tabs.Tab>
          <Tabs.Tab value="direct">
            Прямые <span className={classes.tabCount}>{fmtNumber(c.direct)}</span>
          </Tabs.Tab>
          <Tabs.Tab value="indirect">
            Косвенные <span className={classes.tabCount}>{fmtNumber(c.indirect)}</span>
          </Tabs.Tab>
          <Tabs.Tab value="disputed">
            Спорные <span className={classes.tabCount}>{fmtNumber(c.disputed)}</span>
          </Tabs.Tab>
          <Tabs.Tab value="rejected" ml="auto">
            Отсеяно системой <span className={classes.tabCount}>{fmtNumber(c.rejected)}</span>
          </Tabs.Tab>
        </Tabs.List>
      </Tabs>

      {/* фильтры */}
      <div className={classes.filters}>
        {search.params.platforms.length > 1 && (
          <div className={classes.pills} role="group" aria-label="Площадки">
            <button
              type="button"
              className={classes.pill}
              data-active={f.platform.length === 0 || undefined}
              onClick={() => update({ platform: [] })}
            >
              Все площадки
            </button>
            {search.params.platforms.map((p) => (
              <button
                key={p}
                type="button"
                className={classes.pill}
                data-active={f.platform.includes(p) || undefined}
                aria-pressed={f.platform.includes(p)}
                onClick={() => togglePlatform(p)}
              >
                <PlatformLogo platform={p} size="sm" />
                {PLATFORM_NAME[p]}
              </button>
            ))}
          </div>
        )}
        {!grouped && (
          <div className={classes.sorts} role="group" aria-label="Сортировка">
            {SORT_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                className={classes.sort}
                data-active={f.sort === o.value || undefined}
                aria-pressed={f.sort === o.value}
                onClick={() => update({ sort: o.value })}
              >
                {o.label}
                <span className={classes.sortIndicator} />
              </button>
            ))}
          </div>
        )}
      </div>

      <div className={classes.switches}>
        {f.tab !== "rejected" && (
          <Switch
            size="sm"
            label="Группировать одинаковые новости"
            checked={f.group}
            onChange={(e) => update({ group: e.currentTarget.checked })}
          />
        )}
        {!grouped && (
          <Switch
            size="sm"
            label={`Только без даты (${fmtNumber(c.unknown_date)})`}
            checked={f.unknownDateOnly}
            onChange={(e) => update({ unknownDateOnly: e.currentTarget.checked })}
          />
        )}
        <Switch
          size="sm"
          label={`Показать исключённые (${fmtNumber(c.excluded)})`}
          checked={f.include_excluded}
          onChange={(e) => update({ include_excluded: e.currentTarget.checked })}
        />
      </div>

      {f.target_id.length > 0 && (
        <div className={classes.note}>
          <Icon name="info" />
          Показано найденное в выбранном источнике.
          <button type="button" className={classes.noteAction} onClick={() => update({ target_id: [] })}>
            Показать всё
          </button>
        </div>
      )}
      {f.tab === "rejected" && (
        <div className={classes.note}>
          <Icon name="info" />
          Эти публикации система сочла не относящимися к запросу. Их нет в счёте и в выгрузке.
        </div>
      )}
      {grouped && (
        <div className={classes.note}>
          <Icon name="info" />В счёте каждое размещение — отдельная публикация.
        </div>
      )}

      {/* массовые действия и «Вернуть» — плавающая полоса внизу экрана: появление не сдвигает список
          и не наезжает на липкие шапку и параметры при 200+ результатах */}
      {selected.size > 0 ? (
        <div className={classes.bulk} role="region" aria-label="Действия с выбранными">
          <span>Выбрано: {selected.size}</span>
          <Button size="compact-sm" variant="subtle" color="gray" ml="auto" onClick={() => setSelected(new Set())}>
            Снять выделение
          </Button>
          <Button
            size="compact-sm"
            color="red"
            variant="light"
            leftSection={<Icon name="trash" size={14} />}
            onClick={() => exclude([...selected], true)}
          >
            Исключить выбранные
          </Button>
        </div>
      ) : (
        lastExcluded.length > 0 && (
          <div className={classes.bulk} role="status">
            <Icon name="trash" />
            <span>Исключено: {lastExcluded.length}</span>
            <Button
              size="compact-sm"
              variant="light"
              ml="auto"
              onClick={() => {
                exclusion.mutate({ ids: lastExcluded, excluded: false });
                setLastExcluded([]);
              }}
            >
              Вернуть
            </Button>
            <button type="button" className={classes.noteClose} onClick={() => setLastExcluded([])} aria-label="Скрыть">
              <Icon name="close" size={14} />
            </button>
          </div>
        )
      )}

      {/* список */}
      {active.isSuccess && total === 0 && !running && (
        <div className={classes.empty}>
          <p className={classes.emptyTitle}>Под эти фильтры ничего не подходит</p>
          <p className={classes.emptyText}>Переключите вкладку, площадку или снимите фильтры.</p>
        </div>
      )}
      {active.isSuccess && total === 0 && running && (
        <p className={classes.waiting}>Публикации появятся по мере обработки источников…</p>
      )}
      {/* скелетон, пока список грузится или поиск идёт, а публикаций ещё нет */}
      {(active.isPending || (running && active.isSuccess && total === 0)) && <ListSkeleton />}

      <div className={`${classes.list} mp-stagger`}>
        {grouped
          ? (groups.data?.pages ?? []).flatMap((p) =>
              p.items.map((g) => (
                <GroupCard key={g.group_id} group={g} selected={selected} onSelect={select} onExclude={exclude} />
              )),
            )
          : (list.data?.pages ?? []).flatMap((p) =>
              p.items.map((r) => (
                <ResultCard
                  key={r.id}
                  result={r}
                  selected={selected.has(r.id)}
                  onSelect={(on) => select(r.id, on)}
                  onExclude={(ex) => exclude([r.id], ex)}
                />
              )),
            )}
      </div>

      {active.hasNextPage && (
        <Center>
          <Button variant="default" loading={active.isFetchingNextPage} onClick={() => active.fetchNextPage()}>
            Показать ещё
          </Button>
        </Center>
      )}
      {total > 0 && (
        <p className={classes.footnote}>
          {grouped
            ? `Сюжетов и одиночных публикаций: ${fmtNumber(total)}`
            : `Показано ${publications(pages.reduce((n, p) => n + p.items.length, 0))} из ${fmtNumber(total)}`}
        </p>
      )}
    </section>
  );
}

function ListSkeleton() {
  return (
    <div className={classes.list} aria-busy="true" aria-label="Загрузка подборки">
      {[0, 1, 2].map((i) => (
        <div key={i} className={`${classes.skeleton} mp-signal-loading`}>
          <Skeleton height={40} width={40} radius="md" />
          <div style={{ flex: 1 }}>
            <Skeleton height={14} width="55%" mb="sm" />
            <Skeleton height={10} width="30%" mb="md" />
            <Skeleton height={10} mb={6} />
            <Skeleton height={10} width="80%" />
          </div>
        </div>
      ))}
    </div>
  );
}
