import {
  Alert,
  Anchor,
  Button,
  Center,
  Chip,
  Group,
  Paper,
  Select,
  Skeleton,
  Stack,
  Switch,
  Tabs,
  Text,
} from "@mantine/core";
import { useEffect, useState } from "react";

import type { S } from "../../api/client";
import { PLATFORM_TITLE } from "../../lib/platforms";
import { fmtNumber, publications } from "../../lib/format";
import { useConnectionNotice } from "../../lib/useConnectionNotice";
import { isFinal } from "../search/status";
import { useResultFilters, type Sort, type Tab } from "./filters";
import { GroupCard } from "./GroupCard";
import { ResultCard } from "./ResultCard";
import { useExclusion, useGroupList, useResultList } from "./useResults";

const SORT_OPTIONS: { value: Sort; label: string }[] = [
  { value: "relevance", label: "Сначала самые близкие к запросу" },
  { value: "date_desc", label: "Сначала новые" },
  { value: "date_asc", label: "Сначала старые" },
];

export function ResultsView({ search }: { search: S["Search"] }) {
  const { filters: f, update } = useResultFilters();
  const running = !isFinal(search.status);
  const c = search.counts;
  const grouped = f.group && f.tab !== "rejected";

  const list = useResultList(search.id, f, running, !grouped);
  const groups = useGroupList(search.id, f, running, grouped);
  const active = grouped ? groups : list;
  useConnectionNotice(active);

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

  const pages = active.data?.pages ?? [];
  const total = pages[0]?.total ?? 0;

  return (
    <Stack gap="sm">
      <Tabs value={f.tab} onChange={(v) => update({ tab: (v ?? "all") as Tab })}>
        <Tabs.List>
          <Tabs.Tab value="all">Все {fmtNumber(c.total)}</Tabs.Tab>
          <Tabs.Tab value="direct">Прямые {fmtNumber(c.direct)}</Tabs.Tab>
          <Tabs.Tab value="indirect">Косвенные {fmtNumber(c.indirect)}</Tabs.Tab>
          <Tabs.Tab value="disputed">Спорные {fmtNumber(c.disputed)}</Tabs.Tab>
          <Tabs.Tab value="rejected" ml="auto" c="dimmed">
            Отсеяно системой ({fmtNumber(c.rejected)})
          </Tabs.Tab>
        </Tabs.List>
      </Tabs>

      {/* фильтры */}
      <Group gap="md" wrap="wrap">
        {search.params.platforms.length > 1 && (
          <Chip.Group multiple value={f.platform} onChange={(v) => update({ platform: v as S["Platform"][] })}>
            <Group gap={6}>
              {search.params.platforms.map((p) => (
                <Chip key={p} value={p} size="xs">
                  {PLATFORM_TITLE[p]}
                </Chip>
              ))}
            </Group>
          </Chip.Group>
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
        {f.tab !== "rejected" && (
          <Switch
            size="sm"
            label="Группировать одинаковые новости"
            checked={f.group}
            onChange={(e) => update({ group: e.currentTarget.checked })}
          />
        )}
        {!grouped && (
          <Select
            size="xs"
            ml="auto"
            w={260}
            allowDeselect={false}
            value={f.sort}
            onChange={(v) => update({ sort: (v ?? "relevance") as Sort })}
            data={SORT_OPTIONS}
            aria-label="Сортировка"
          />
        )}
      </Group>

      {f.target_id.length > 0 && (
        <Alert variant="light" color="blue" p="xs">
          Показано найденное в выбранном источнике.{" "}
          <Anchor component="button" type="button" size="sm" onClick={() => update({ target_id: [] })}>
            Показать всё
          </Anchor>
        </Alert>
      )}
      {f.tab === "rejected" && (
        <Text size="sm" c="dimmed">
          Эти публикации система сочла не относящимися к запросу. Их нет в счёте и в выгрузке.
        </Text>
      )}
      {grouped && (
        <Text size="sm" c="dimmed">
          В счёте каждое размещение — отдельная публикация.
        </Text>
      )}

      {/* массовые действия и «Вернуть» */}
      {selected.size > 0 && (
        <Paper withBorder p="xs" radius="md">
          <Group justify="space-between">
            <Text size="sm">Выбрано: {selected.size}</Text>
            <Group gap="xs">
              <Button size="compact-sm" variant="subtle" color="gray" onClick={() => setSelected(new Set())}>
                Снять выделение
              </Button>
              <Button size="compact-sm" color="red" variant="light" onClick={() => exclude([...selected], true)}>
                Исключить выбранные
              </Button>
            </Group>
          </Group>
        </Paper>
      )}
      {lastExcluded.length > 0 && (
        <Alert variant="light" color="gray" p="xs" withCloseButton onClose={() => setLastExcluded([])}>
          Исключено: {lastExcluded.length}.{" "}
          <Anchor
            component="button"
            type="button"
            size="sm"
            onClick={() => {
              exclusion.mutate({ ids: lastExcluded, excluded: false });
              setLastExcluded([]);
            }}
          >
            Вернуть
          </Anchor>
        </Alert>
      )}

      {/* список */}
      {active.isSuccess && total === 0 && (
        <Text c="dimmed" py="xs">
          {running ? "Публикации появятся по мере обработки источников…" : "Под эти фильтры ничего не подходит."}
        </Text>
      )}
      {/* скелетон, пока список грузится или поиск идёт, а публикаций ещё нет */}
      {(active.isPending || (running && active.isSuccess && total === 0)) && <ListSkeleton />}
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

      {active.hasNextPage && (
        <Center>
          <Button variant="default" loading={active.isFetchingNextPage} onClick={() => active.fetchNextPage()}>
            Показать ещё
          </Button>
        </Center>
      )}
      {total > 0 && (
        <Text size="xs" c="dimmed" ta="center">
          {grouped ? `Сюжетов и одиночных публикаций: ${fmtNumber(total)}` : `Показано ${publications(pages.reduce((n, p) => n + p.items.length, 0))} из ${fmtNumber(total)}`}
        </Text>
      )}
    </Stack>
  );
}

function ListSkeleton() {
  return (
    <Stack gap="sm" aria-busy="true" aria-label="Загрузка подборки">
      {[0, 1, 2].map((i) => (
        <Paper key={i} withBorder radius="md" p="md">
          <Skeleton height={12} width="30%" mb="sm" />
          <Skeleton height={10} mb={6} />
          <Skeleton height={10} width="85%" mb={6} />
          <Skeleton height={10} width="60%" />
        </Paper>
      ))}
    </Stack>
  );
}
