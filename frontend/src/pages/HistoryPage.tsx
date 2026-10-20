// История поисков (FE-09): GET /searches, «Показать ещё» по has_more, клик по карточке → /search/:id.
import { Alert, Anchor, Button, Center, Skeleton } from "@mantine/core";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api, unwrap, type S } from "../api/client";
import { Icon } from "../components/Icon";
import { PlatformLogo } from "../components/PlatformLogo";
import { ScanOrbit } from "../components/Signal";
import { isFinal, SEARCH_STATUS } from "../features/search/status";
import { fmtDateTime, fmtPeriod } from "../lib/dates";
import { errorText } from "../lib/errors";
import { publications } from "../lib/format";
import classes from "./HistoryPage.module.css";

const PAGE = 30;
const cut = (s: string, n: number) => {
  const one = s.replace(/\s+/g, " ").trim();
  return one.length > n ? `${one.slice(0, n - 1).trimEnd()}…` : one;
};

// цвет точки статуса — как во всём приложении: идёт — синий, готово — зелёный, частично — жёлтый, ошибка — красный
const DOT: Record<S["SearchStatus"], string> = {
  queued: "#c5c9ba",
  running: "#60a5fa",
  completed: "#34d399",
  partial: "#fbbf24",
  failed: "#f87171",
  cancelled: "#979b8d",
};

export function HistoryPage() {
  const history = useInfiniteQuery({
    queryKey: ["searches", "history"],
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/api/v1/searches", { params: { query: { limit: PAGE, offset: pageParam } } })),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => (last.has_more ? pages.reduce((n, p) => n + p.items.length, 0) : undefined),
    // пока какой-то поиск в списке идёт — обновляем его статус
    refetchInterval: (q) => (q.state.data?.pages.some((p) => p.items.some((s) => !isFinal(s.status))) ? 5000 : false),
  });
  const items = history.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className={`mp-container mp-page-enter ${classes.page}`}>
      <div className={classes.head}>
        <div>
          <div className="mp-eyebrow">
            <ScanOrbit />
            Обновляется автоматически
          </div>
          <h1 className="mp-page-title" style={{ marginTop: 12 }}>
            История
          </h1>
          <p className="mp-page-lead">Ваши подборки в этом браузере — с параметрами и результатами. Другим пользователям они не видны.</p>
        </div>
        <Link to="/search" className="mp-accent-button mp-press">
          <Icon name="plus" /> Новый поиск
        </Link>
      </div>

      {history.isError && !history.data && (
        <Alert color="red" title="Не удалось загрузить историю">
          {errorText(history.error)}{" "}
          <Anchor component="button" type="button" size="sm" onClick={() => history.refetch()}>
            Повторить
          </Anchor>
        </Alert>
      )}

      {history.isSuccess && items.length === 0 && (
        <div className={classes.empty}>
          <p className={classes.emptyTitle}>Поисков ещё не было</p>
          <p className={classes.emptyText}>Запустите первый поиск — подборка появится здесь.</p>
        </div>
      )}

      <div className={`${classes.list} mp-stagger`}>
        {history.isPending &&
          [0, 1, 2, 3].map((i) => (
            <div key={i} className={classes.card}>
              <Skeleton height={14} width="50%" mb="sm" />
              <Skeleton height={10} width="30%" />
            </div>
          ))}
        {items.map((s) => (
          <HistoryCard key={s.id} s={s} />
        ))}
      </div>

      {history.hasNextPage && (
        <Center>
          <Button variant="default" loading={history.isFetchingNextPage} onClick={() => history.fetchNextPage()}>
            Показать ещё
          </Button>
        </Center>
      )}
    </div>
  );
}

function HistoryCard({ s }: { s: S["SearchSummary"] }) {
  const st = SEARCH_STATUS[s.status];
  const p = s.params;
  const running = !isFinal(s.status);
  return (
    <Link to={`/search/${s.id}`} className={`${classes.card} mp-signal-card mp-motion-card`} data-lift="soft" aria-label={`Открыть поиск «${cut(p.query, 60)}»`}>
      <div className={classes.cardTop}>
        <span className={classes.status}>
          <span className={`mp-dot ${running ? "mp-pulse" : ""}`} style={{ background: DOT[s.status] }} />
          {st.label}
        </span>
        <span>·</span>
        <span>{fmtDateTime(s.created_at)}</span>
        <span className={classes.found}>{isFinal(s.status) ? publications(s.counts.total) : "идёт поиск…"}</span>
      </div>
      <h2 className={classes.query} title={p.query.length > 140 ? p.query : undefined}>
        {cut(p.query, 140)}
      </h2>
      <div className={classes.cardBottom}>
        <span className={classes.meta}>
          <Icon name="calendar" size={14} />
          {fmtPeriod(p.period_from, p.period_to)}
        </span>
        <span className={classes.meta}>{p.mode === "selected" ? "Мои источники" : "Везде"}</span>
        <span className={classes.logos}>
          {p.platforms.map((x) => (
            <PlatformLogo key={x} platform={x} size="sm" />
          ))}
        </span>
        <span className={classes.open}>
          Открыть подборку <Icon name="arrow" />
        </span>
      </div>
    </Link>
  );
}
