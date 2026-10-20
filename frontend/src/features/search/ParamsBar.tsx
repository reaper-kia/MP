import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { api, unwrap, type S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { PlatformLogo } from "../../components/PlatformLogo";
import { fmtDateTime, fmtPeriod } from "../../lib/dates";
import { errorText } from "../../lib/errors";
import { plural, publications } from "../../lib/format";
import classes from "./ParamsBar.module.css";

const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);

/** К каким условиям относится показанная подборка. Липнет под шапкой при прокрутке. */
export function ParamsBar({ search, dirty }: { search: S["Search"]; dirty: boolean }) {
  const p = search.params;
  const period = fmtPeriod(p.period_from, p.period_to);

  return (
    <div className={classes.sticky}>
      <div className={classes.bar}>
        <span className={classes.query} title={p.query.length > 80 ? p.query : undefined}>
          «{cut(p.query.replace(/\s+/g, " "), 80)}»
        </span>
        <span className={classes.meta}>
          <Icon name="calendar" size={14} />
          {period}
        </span>
        <span className={classes.meta}>{p.mode === "selected" ? "Мои источники" : "Везде"}</span>
        <span className={classes.logos}>
          {p.platforms.map((x) => (
            <PlatformLogo key={x} platform={x} size="sm" />
          ))}
        </span>
        <span className={classes.count}>{publications(search.counts.total)}</span>
      </div>
      {search.cache && !dirty && <CacheNote search={search} cache={search.cache} />}
      {dirty && (
        <div className={classes.dirty}>
          <Icon name="info" />
          <span>Параметры изменены. Ниже — подборка по прежним условиям.</span>
          {/* сабмит формы поиска по id — та же валидация, что у кнопки «Найти» */}
          <button type="submit" form="search-form" className={classes.again}>
            Найти заново
          </button>
        </div>
      )}
    </div>
  );
}

/** «собрана 12 мин назад» — от момента, когда исходный поиск завершился. */
export function collectedAgo(iso: string, now = Date.now()): string {
  const minutes = Math.floor((now - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.floor(minutes / 60);
  return `${hours} ${plural(hours, ["час", "часа", "часов"])} назад`;
}

/** Копия недавнего такого же поиска (B2-20): когда собрана и «Обновить» — тот же поиск мимо кэша. */
function CacheNote({ search, cache }: { search: S["Search"]; cache: S["SearchCache"] }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const refresh = useMutation({
    mutationFn: () => {
      const p = search.params;
      return unwrap(
        api.POST("/api/v1/searches", {
          body: {
            query: p.query,
            period_from: p.period_from,
            period_to: p.period_to,
            mode: p.mode,
            platforms: p.platforms,
            source_ids: p.source_ids,
            fresh: true,
          },
        }),
      );
    },
    onSuccess: (fresh) => {
      queryClient.setQueryData(["search", fresh.id], fresh);
      queryClient.invalidateQueries({ queryKey: ["searches"] });
      navigate(`/search/${fresh.id}`);
    },
    onError: (err) => notifications.show({ color: "red", title: "Поиск не запущен", message: errorText(err) }),
  });

  return (
    <div className={classes.cache}>
      <Icon name="history" size={14} />
      <span title={fmtDateTime(cache.created_at) ?? undefined}>
        Подборка из кэша · собрана {collectedAgo(cache.created_at, now)}
      </span>
      <button type="button" className={classes.again} onClick={() => refresh.mutate()} disabled={refresh.isPending}>
        {refresh.isPending ? "Запускаем…" : "Обновить"}
      </button>
    </div>
  );
}
