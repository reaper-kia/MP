// Окошко расширения (FE-17): выделенный текст → поиск размещений → компактная подборка.
// Поиск идёт в service worker (background.ts); здесь — показ состояния из chrome.storage.session.
import { Button, Loader, Progress, SegmentedControl, Textarea, UnstyledButton } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, setApiServer, unwrap, type S } from "../api/client";
import { Icon } from "../components/Icon";
import { PlatformLogo } from "../components/PlatformLogo";
import { RELEVANCE } from "../features/results/relevance";
import { isFinal, stageText } from "../features/search/status";
import { failedTargets, failureReason, foundCount, viewState } from "../features/search/viewState";
import { fmtDateTime, fmtPeriod } from "../lib/dates";
import { errorText } from "../lib/errors";
import { fmtNumber, publications } from "../lib/format";
import { AddPage } from "./AddPage";
import classes from "./popup.module.css";
import { loadSettings, type ExtSettings } from "./settings";
import { mount, openTab } from "./shared";
import { loadRun, NO_CONNECTION, type ExtMessage, type RunState } from "./state";

const send = (msg: ExtMessage) => chrome.runtime.sendMessage(msg);

const REL_SHORT: Record<S["Relevance"], string> = {
  direct: "Прямая",
  indirect: "Косвенная",
  disputed: "Спорно",
  rejected: RELEVANCE.rejected.label,
};

function useRun() {
  const [run, setRun] = useState<RunState | null | undefined>(undefined);
  useEffect(() => {
    void loadRun().then(setRun);
    const onChange = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === "session" && "run" in changes) setRun((changes.run.newValue as RunState | undefined) ?? null);
    };
    chrome.storage.onChanged.addListener(onChange);
    return () => chrome.storage.onChanged.removeListener(onChange);
  }, []);
  return run;
}

function useSettings() {
  const [settings, setSettings] = useState<ExtSettings | null>(null);
  useEffect(() => {
    void loadSettings().then((s) => {
      setApiServer(s.server);
      setSettings(s);
    });
  }, []);
  return settings;
}

/** Выделенный на странице текст (activeTab даётся кликом по значку расширения). */
async function pageSelection(): Promise<string> {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return "";
    const [res] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => getSelection()?.toString() ?? "",
    });
    return typeof res?.result === "string" ? res.result.trim() : "";
  } catch {
    return ""; // chrome://, магазин расширений и т.п. — скрипты туда не пускают
  }
}

function Popup() {
  const run = useRun();
  const settings = useSettings();
  if (run === undefined || !settings) {
    return (
      <div className={classes.center}>
        <Loader size="sm" />
      </div>
    );
  }
  const server = run?.server ?? settings.server;
  return (
    <div className={classes.shell}>
      <header className={classes.header}>
        <span className={classes.logo}>
          <Icon name="logo" size={16} />
        </span>
        <span className={classes.brand}>МедиаПульс</span>
        <span className={classes.headerSub}>Где ещё опубликовано</span>
        <UnstyledButton
          className={classes.iconButton}
          onClick={() => chrome.runtime.openOptionsPage()}
          aria-label="Настройки"
          title="Настройки"
        >
          <Icon name="filter" size={16} />
        </UnstyledButton>
      </header>
      <main className={classes.main}>{run ? <RunView run={run} /> : <StartForm settings={settings} />}</main>
      <footer className={classes.footer}>
        {run?.searchId && (
          <button type="button" className={classes.footerLink} onClick={() => openTab(`${server}/search/${run.searchId}`)}>
            Открыть подборку на сайте <Icon name="external" size={14} />
          </button>
        )}
        <button type="button" className={classes.footerLink} onClick={() => openTab(`${server}/`)}>
          Открыть МедиаПульс <Icon name="external" size={14} />
        </button>
      </footer>
    </div>
  );
}

function StartForm({ settings }: { settings: ExtSettings }) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState(settings.mode);
  const [days, setDays] = useState(settings.days);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    void pageSelection().then((t) => t && setQuery((q) => q || t));
  }, []);

  const submit = async () => {
    const q = query.trim();
    if (q.length < 3) {
      setError("Опишите тему, событие, человека или вставьте текст поста — хотя бы 3 символа");
      return;
    }
    if (q.length > 20000) {
      setError("Слишком длинный текст — не больше 20 000 символов");
      return;
    }
    setStarting(true);
    await send({ type: "start", query: q, mode, days });
  };

  return (
    <form
      className={classes.form}
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <Textarea
        autosize
        minRows={4}
        maxRows={9}
        autoFocus
        placeholder="Вставьте или выделите текст поста"
        value={query}
        onChange={(e) => {
          setQuery(e.currentTarget.value);
          setError(null);
        }}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === "Enter") void submit();
        }}
        error={error}
        aria-label="Текст поста или запрос"
      />
      <div className={classes.formRow}>
        <SegmentedControl
          size="xs"
          value={mode}
          onChange={(v) => setMode(v as typeof mode)}
          data={[
            { value: "selected", label: "Мои источники" },
            { value: "global", label: "Везде" },
          ]}
        />
        <SegmentedControl
          size="xs"
          value={String(days)}
          onChange={(v) => setDays(v === "7" ? 7 : 30)}
          data={[
            { value: "7", label: "7 дней" },
            { value: "30", label: "30 дней" },
          ]}
        />
      </div>
      <Button type="submit" fullWidth loading={starting} leftSection={<Icon name="search" size={16} />}>
        Найти размещения
      </Button>
      <p className={classes.hint}>
        Выделите текст на странице и откройте окошко — или правая кнопка → «Найти размещения в МедиаПульс».
      </p>
      <AddPage />
    </form>
  );
}

function RunView({ run }: { run: RunState }) {
  const [queryOpen, setQueryOpen] = useState(false);
  const s = run.search;
  const final = !!s && isFinal(s.status);
  const offline = run.error === NO_CONNECTION;

  return (
    <div className={classes.run}>
      <div className={classes.queryBox}>
        <button
          type="button"
          className={classes.query}
          data-open={queryOpen || undefined}
          onClick={() => setQueryOpen((x) => !x)}
          title={queryOpen ? "Свернуть" : "Показать полностью"}
        >
          {run.query}
        </button>
        <p className={classes.meta}>
          {fmtPeriod(run.periodFrom, run.periodTo)} · {run.mode === "selected" ? "мои источники" : "везде"}
          <button type="button" className={classes.newSearch} onClick={() => void send({ type: "reset" })}>
            Новый поиск
          </button>
        </p>
      </div>

      {run.error ? (
        <div className={classes.banner} data-tone="red">
          <p className={classes.bannerTitle}>{offline ? "Нет связи с сервером" : "Поиск не выполнен"}</p>
          <p className={classes.bannerText}>{offline ? `Сервер ${run.server} не отвечает. Проверьте адрес в настройках.` : run.error}</p>
          <Button
            size="compact-sm"
            variant="default"
            mt={8}
            leftSection={<Icon name="refresh" size={14} />}
            onClick={() => void send({ type: "start", query: run.query, mode: run.mode, days: run.days })}
          >
            Повторить
          </Button>
        </div>
      ) : final ? (
        <Final search={s!} />
      ) : (
        <Running run={run} />
      )}
    </div>
  );
}

function Running({ run }: { run: RunState }) {
  const s = run.search;
  const queued = !!s && (s.status === "queued" || s.stage === "queued");
  return (
    <div className={classes.progress}>
      <p className={classes.stage}>
        {!s ? "Запускаем поиск…" : queued ? "В очереди — дождитесь окончания предыдущего поиска" : stageText(s)}
      </p>
      <Progress value={s?.progress.percent ?? 0} animated striped size="sm" radius="xl" />
      <p className={classes.progressMeta}>
        <span>Обычно 1–3 минуты · окошко можно закрыть</span>
        <span className={classes.found}>Найдено пока: {fmtNumber(s?.counts.total ?? 0)}</span>
      </p>
      <Button
        size="compact-sm"
        variant="default"
        leftSection={<Icon name={queued ? "close" : "stop"} size={14} />}
        onClick={() => void send({ type: "cancel" })}
      >
        {queued ? "Отменить" : "Остановить"}
      </Button>
    </div>
  );
}

function Final({ search }: { search: S["Search"] }) {
  const v = viewState(search);
  const found = foundCount(search);
  const results = useQuery({
    queryKey: ["ext-results", search.id, search.counts.total],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/searches/{search_id}/results", {
          params: { path: { search_id: search.id }, query: { sort: "relevance", limit: 20 } },
        }),
      ),
    enabled: found > 0,
  });

  return (
    <>
      {(v === "failed" || v === "failed_with_results") && (
        <Banner tone="red" title="Поиск не выполнен" text={failureReason(search) ?? "Ни один источник не удалось обработать."} />
      )}
      {v === "cancelled" && <Banner tone="gray" title="Поиск остановлен" />}
      {v === "empty" && (
        <Banner
          tone="gray"
          title="Подходящие публикации не найдены"
          text="Расширьте период, попробуйте «Везде» или опишите тему другими словами."
        />
      )}
      {v === "partial" && (
        <Banner
          tone="amber"
          title={`Не удалось обработать источников: ${failedTargets(search).length}`}
          text="Подборка собрана по остальным — подробности и «Повторить» на сайте."
        />
      )}

      {found > 0 && (
        <>
          <p className={classes.total}>
            Найдено {publications(search.counts.total)}
            {search.counts.total > 20 && <span className={classes.totalNote}> · здесь 20 самых близких</span>}
          </p>
          {results.isPending && <Loader size="sm" mx="auto" display="block" />}
          {results.isError && <p className={classes.bannerText}>{errorText(results.error)}</p>}
          <div className={classes.list}>
            {results.data?.items.map((r) => (
              <ResultRow key={r.id} r={r} />
            ))}
          </div>
        </>
      )}
    </>
  );
}

function Banner({ tone, title, text }: { tone: "red" | "amber" | "gray"; title: string; text?: string }) {
  return (
    <div className={classes.banner} data-tone={tone}>
      <p className={classes.bannerTitle}>{title}</p>
      {text && <p className={classes.bannerText}>{text}</p>}
    </div>
  );
}

function ResultRow({ r }: { r: S["Result"] }) {
  const [open, setOpen] = useState(false);
  const date = fmtDateTime(r.published_at);
  return (
    <div className={classes.item} data-open={open || undefined}>
      <button type="button" className={classes.itemHead} onClick={() => setOpen((x) => !x)} aria-expanded={open}>
        <PlatformLogo platform={r.platform} size="sm" title={null} />
        <span className={classes.itemTitle}>{r.title}</span>
        <span className={classes.rel} data-rel={r.relevance}>
          {REL_SHORT[r.relevance]}
        </span>
        <span className={classes.score}>{Math.round(r.score * 100)}%</span>
      </button>
      {open && (
        <div className={classes.itemBody}>
          <p className={classes.itemMeta}>
            {r.source.name} · {date ?? "Дата недоступна"}
          </p>
          <p className={classes.excerpt}>
            {r.excerpt_parts.map((p, i) => (p.highlight ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}
          </p>
          {r.explanation && (
            <p className={classes.explanation}>
              <Icon name="sparkles" size={13} />
              {r.explanation}
            </p>
          )}
          <a href={r.url} target="_blank" rel="noopener noreferrer" className={classes.postLink}>
            Открыть пост <Icon name="external" size={13} />
          </a>
        </div>
      )}
    </div>
  );
}

mount(<Popup />);
