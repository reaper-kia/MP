// Итог поиска (FE-06): баннеры partial / failed / cancelled и экран «ничего не найдено».
// Какой из них показать, решает только viewState().
import { Alert, Anchor, Button, Group, List, Paper, Stack, Text, Title } from "@mantine/core";

import type { S } from "../../api/client";
import { fmtPeriod } from "../../lib/dates";
import { plural, publications, sourcesCount } from "../../lib/format";
import { PLATFORM_TITLE } from "../../lib/platforms";
import { useResultFilters } from "../results/filters";
import { STATUS_COLOR } from "./status";
import { useRetry } from "./useSearch";
import { failedTargets, failureReason, foundCount, viewState } from "./viewState";

export function SearchOutcome({ search }: { search: S["Search"] }) {
  const v = viewState(search);
  switch (v) {
    case "partial":
      return <PartialBanner search={search} />;
    case "empty":
      return (
        <Stack gap="sm">
          {search.status === "partial" && <PartialBanner search={search} />}
          <EmptyResult search={search} />
        </Stack>
      );
    case "failed":
    case "failed_with_results":
      return <FailedBanner search={search} withResults={v === "failed_with_results"} />;
    case "cancelled":
      return <CancelledBanner search={search} />;
    default:
      return null;
  }
}

function RetryButton({ search, color }: { search: S["Search"]; color: string }) {
  const retry = useRetry(search.id);
  if (failedTargets(search).length === 0) return null;
  return (
    <Button size="compact-sm" color={color} loading={retry.isPending} onClick={() => retry.mutate(undefined)}>
      Повторить
    </Button>
  );
}

/** Какие источники не удалось обработать — до трёх с причиной, остальные числом. */
function FailedList({ targets }: { targets: S["SearchTarget"][] }) {
  const shown = targets.slice(0, 3);
  return (
    <Stack gap={2} mt={4}>
      {shown.map((t) => (
        <Text key={t.id} size="sm">
          {PLATFORM_TITLE[t.platform]} · {t.name}
          {t.error?.message ? ` — ${t.error.message}` : ""}
        </Text>
      ))}
      {targets.length > shown.length && (
        <Text size="sm" c="dimmed">
          и ещё {sourcesCount(targets.length - shown.length)} — список в «Где искали»
        </Text>
      )}
    </Stack>
  );
}

function PartialBanner({ search }: { search: S["Search"] }) {
  const failed = failedTargets(search);
  const n = failed.length;
  return (
    <Alert color={STATUS_COLOR.partial} variant="light" title={`Не удалось обработать ${n} ${plural(n, ["источник", "источника", "источников"])}`}>
      <Group justify="space-between" align="flex-end" wrap="nowrap">
        <div>
          <Text size="sm">Подборка собрана по остальным источникам. Можно попробовать ещё раз.</Text>
          <FailedList targets={failed} />
        </div>
        <RetryButton search={search} color={STATUS_COLOR.partial} />
      </Group>
    </Alert>
  );
}

function FailedBanner({ search, withResults }: { search: S["Search"]; withResults: boolean }) {
  const reason = failureReason(search);
  return (
    <Alert color={STATUS_COLOR.failed} variant="light" title="Поиск не выполнен">
      <Group justify="space-between" align="flex-end" wrap="nowrap">
        <div>
          <Text size="sm">{reason ?? "Ни один источник не удалось обработать."}</Text>
          {withResults && (
            <Text size="sm" mt={4}>
              Ниже — что успели найти до ошибки: {publications(foundCount(search))}.
            </Text>
          )}
        </div>
        <RetryButton search={search} color={STATUS_COLOR.failed} />
      </Group>
    </Alert>
  );
}

function CancelledBanner({ search }: { search: S["Search"] }) {
  const found = foundCount(search);
  return (
    <Alert color={STATUS_COLOR.neutral} variant="light" title="Поиск остановлен">
      <Group justify="space-between" align="flex-end" wrap="nowrap">
        <Text size="sm">
          {found > 0 ? `Ниже — что успели найти до остановки: ${publications(found)}.` : "До остановки ничего не нашлось."}
        </Text>
        {/* сабмит формы поиска сверху — запустит поиск с теми же (или изменёнными) параметрами */}
        <Button size="compact-sm" variant="default" type="submit" form="search-form">
          Запустить заново
        </Button>
      </Group>
    </Alert>
  );
}

/** Где искали — словами: «5 источников (VK, OK), 12.10–19.10.2026» / «везде — VK, OK, 12.10–19.10.2026». */
export function searchedWhere(search: S["Search"]): string {
  const p = search.params;
  const platforms = p.platforms.map((x) => PLATFORM_TITLE[x]).join(", ");
  const period = fmtPeriod(p.period_from, p.period_to);
  if (p.mode === "global") return `везде — ${platforms}, ${period}`;
  const n = search.targets.filter((t) => t.kind === "source").length || p.source_ids.length;
  return `${sourcesCount(n)} (${platforms}), ${period}`;
}

function EmptyResult({ search }: { search: S["Search"] }) {
  const { update } = useResultFilters();
  const rejected = search.counts.rejected;
  return (
    <Paper withBorder radius="md" p="xl">
      <Stack gap="sm" maw={640}>
        <Title order={3}>Подходящие публикации не найдены</Title>
        <Text>Искали: {searchedWhere(search)}.</Text>
        <Text size="sm" c="dimmed">
          Что можно сделать:
        </Text>
        <List size="sm" spacing={4}>
          <List.Item>Расширьте период</List.Item>
          {search.params.mode === "selected" && <List.Item>Попробуйте режим «Везде»</List.Item>}
          <List.Item>Переформулируйте запрос — опишите тему другими словами</List.Item>
        </List>
        {rejected > 0 && (
          <Text size="sm" c="dimmed">
            Система отсеяла {publications(rejected)} как не относящиеся к запросу.{" "}
            <Anchor component="button" type="button" size="sm" onClick={() => update({ tab: "rejected" })}>
              Посмотреть отсеянные
            </Anchor>
          </Text>
        )}
      </Stack>
    </Paper>
  );
}
