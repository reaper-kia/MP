// Итог поиска (FE-06): баннеры partial / failed / cancelled и экран «ничего не найдено».
// Какой из них показать, решает только viewState().
import { Button } from "@mantine/core";
import type { ReactNode } from "react";

import type { S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { PlatformLogo } from "../../components/PlatformLogo";
import { fmtPeriod } from "../../lib/dates";
import { plural, publications, sourcesCount } from "../../lib/format";
import { PLATFORM_TITLE } from "../../lib/platforms";
import { useResultFilters } from "../results/filters";
import classes from "./SearchOutcome.module.css";
import { useNoGlobal } from "./useCatalog";
import { useRetry } from "./useSearch";
import { failedTargets, failureReason, foundCount, targetName, viewState } from "./viewState";

export function SearchOutcome({ search }: { search: S["Search"] }) {
  const v = viewState(search, useNoGlobal());
  switch (v) {
    case "partial":
      return <PartialBanner search={search} />;
    case "empty":
      return (
        <>
          {search.status === "partial" && <PartialBanner search={search} />}
          <EmptyResult search={search} />
        </>
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

function Banner({ tone, title, children, action }: { tone: "amber" | "red" | "gray"; title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className={classes.banner} data-tone={tone}>
      <Icon name="info" size={18} className={classes.bannerIcon} />
      <div className={classes.bannerBody}>
        <p className={classes.bannerTitle}>{title}</p>
        {children}
      </div>
      {action && <div className={classes.bannerAction}>{action}</div>}
    </div>
  );
}

function RetryButton({ search }: { search: S["Search"] }) {
  const retry = useRetry(search.id);
  const failed = failedTargets(search, useNoGlobal());
  if (failed.length === 0) return null;
  return (
    <Button
      size="compact-sm"
      variant="default"
      leftSection={<Icon name="refresh" size={14} />}
      loading={retry.isPending}
      onClick={() => retry.mutate(failed.map((t) => t.id))}
    >
      Повторить
    </Button>
  );
}

/** Какие источники не удалось обработать — до трёх с причиной, остальные числом. */
function FailedList({ targets }: { targets: S["SearchTarget"][] }) {
  const shown = targets.slice(0, 3);
  return (
    <div className={classes.failedList}>
      {shown.map((t) => (
        <p key={t.id} className={classes.failedItem}>
          <PlatformLogo platform={t.platform} size="sm" />
          <span className="mp-clamp-2" title={t.error?.message ? `${targetName(t)} — ${t.error.message}` : undefined}>
            <b>{targetName(t)}</b>
            {t.error?.message ? ` — ${t.error.message}` : ""}
          </span>
        </p>
      ))}
      {targets.length > shown.length && (
        <p className={classes.text}>и ещё {sourcesCount(targets.length - shown.length)} — список в «Где искали»</p>
      )}
    </div>
  );
}

function PartialBanner({ search }: { search: S["Search"] }) {
  const failed = failedTargets(search, useNoGlobal());
  const n = failed.length;
  if (n === 0) return null;
  return (
    <Banner
      tone="amber"
      title={`Не удалось обработать ${n} ${plural(n, ["источник", "источника", "источников"])}`}
      action={<RetryButton search={search} />}
    >
      <p className={classes.text}>Подборка собрана по остальным источникам. Можно попробовать ещё раз.</p>
      <FailedList targets={failed} />
    </Banner>
  );
}

function FailedBanner({ search, withResults }: { search: S["Search"]; withResults: boolean }) {
  const reason = failureReason(search, useNoGlobal());
  return (
    <Banner tone="red" title="Поиск не выполнен" action={<RetryButton search={search} />}>
      <p className={`${classes.text} mp-clamp-2`} title={reason ?? undefined}>
        {reason ?? "Ни один источник не удалось обработать."}
      </p>
      {withResults && (
        <p className={classes.text}>Ниже — что успели найти до ошибки: {publications(foundCount(search))}.</p>
      )}
    </Banner>
  );
}

function CancelledBanner({ search }: { search: S["Search"] }) {
  const found = foundCount(search);
  return (
    <Banner
      tone="gray"
      title="Поиск остановлен"
      action={
        // сабмит формы поиска сверху — запустит поиск с теми же (или изменёнными) параметрами
        <Button size="compact-sm" variant="default" type="submit" form="search-form" leftSection={<Icon name="refresh" size={14} />}>
          Запустить заново
        </Button>
      }
    >
      <p className={classes.text}>
        {found > 0 ? `Ниже — что успели найти до остановки: ${publications(found)}.` : "До остановки ничего не нашлось."}
      </p>
    </Banner>
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
    <div className={classes.empty}>
      <p className={classes.emptyTitle}>Подходящие публикации не найдены</p>
      <p className={classes.emptyText}>Искали: {searchedWhere(search)}.</p>
      <ul className={classes.tips}>
        <li>Расширьте период</li>
        {search.params.mode === "selected" && <li>Попробуйте режим «Везде»</li>}
        <li>Переформулируйте запрос — опишите тему другими словами</li>
      </ul>
      {rejected > 0 && (
        <p className={classes.emptyText}>
          Система отсеяла {publications(rejected)} как не относящиеся к запросу.{" "}
          <button type="button" className={classes.link} onClick={() => update({ tab: "rejected" })}>
            Посмотреть отсеянные
          </button>
        </p>
      )}
    </div>
  );
}
