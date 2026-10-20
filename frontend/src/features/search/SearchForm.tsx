import { Popover, SegmentedControl, Textarea, Tooltip } from "@mantine/core";
// @mantine/dates — только здесь: календарь грузится вместе со страницей поиска, а не на главной (FE-16)
import "@mantine/dates/styles.css";
import { DatePicker, DatesProvider } from "@mantine/dates";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { api, unwrap, type S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { PlatformLogo } from "../../components/PlatformLogo";
import { DataPulse } from "../../components/Signal";
import { todayYmd } from "../../lib/dates";
import { errorText, fieldErrors } from "../../lib/errors";
import { sourcesCount } from "../../lib/format";
import { PLATFORM_NAME, PLATFORM_TITLE } from "../../lib/platforms";
import { detectPreset, periodLabel, presetPeriod, PRESETS, type Period, type PeriodPreset } from "./period";
import classes from "./SearchForm.module.css";
import { loadSelection, saveSelection } from "./sourceSelection";
import { SourcePicker } from "./SourcePicker";
import { useAllSources, usePlatforms } from "./useCatalog";

const QUERY_TYPE_TEXT: Record<S["QueryType"], string> = {
  topic: "Тема",
  event: "Событие",
  person: "Человек",
  news_text: "Текст новости — ищем её размещения",
};

type Errors = Partial<Record<"query" | "period" | "platforms" | "sources" | "mode", string>>;

// поле из details[].field сервера → поле формы
const SERVER_FIELD: Record<string, keyof Errors> = {
  query: "query",
  period_from: "period",
  period_to: "period",
  platforms: "platforms",
  source_ids: "sources",
  mode: "mode",
};

interface Props {
  /** Параметры показанного поиска: форма над подборкой заполняется ими, а не локальным состоянием. */
  initial?: S["SearchParams"];
  /** Сообщает, отличаются ли текущие значения формы от initial (для баннера «Параметры изменены»). */
  onDirtyChange?: (dirty: boolean) => void;
}

// Частые темы края из макета v2 — просто дописываются в текст запроса
const POPULAR_TAGS = ["#Красноярск", "#КрасноярскийКрай", "#БезопасныеДороги", "#Дороги", "#ГИБДД"];

const tagRe = (tag: string) => new RegExp(`(^|\\s)${tag}(?=\\s|$)`, "iu");
const hasTag = (q: string, tag: string) => tagRe(tag).test(q);
const toggleTag = (q: string, tag: string) =>
  hasTag(q, tag)
    ? q.replace(tagRe(tag), "$1").replace(/\s{2,}/g, " ").trim()
    : q.trim()
      ? `${q.trim()} ${tag}`
      : tag;

const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));

export function SearchForm({ initial, onDirtyChange }: Props) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const platformsQ = usePlatforms();
  const sourcesQ = useAllSources();
  const [pickerOpened, picker] = useDisclosure(false);

  const [query, setQuery] = useState(initial?.query ?? "");
  const [preset, setPreset] = useState<PeriodPreset>(() =>
    initial ? detectPreset([initial.period_from, initial.period_to]) : "7d",
  );
  const [period, setPeriod] = useState<Period>(() =>
    initial ? [initial.period_from, initial.period_to] : presetPeriod("7d"),
  );
  const [mode, setMode] = useState<S["SearchParams"]["mode"]>(initial?.mode ?? "selected");
  // null — «по умолчанию», пока пользователь ничего не трогал
  const [platformsSel, setPlatformsSel] = useState<S["Platform"][] | null>(initial?.platforms ?? null);
  const [sourceSel, setSourceSel] = useState<string[] | null>(() =>
    initial ? (initial.mode === "selected" ? initial.source_ids : null) : loadSelection(),
  );
  const [errors, setErrors] = useState<Errors>({});

  const platformInfo = platformsQ.data ?? [];
  const available = platformInfo.filter((p) => p.status !== "unavailable").map((p) => p.code);
  const platforms = platformsSel ?? available;
  const catalog = sourcesQ.data?.items ?? [];
  const sourceIds = (sourceSel ?? catalog.filter((s) => s.is_active).map((s) => s.id)).filter((id) => {
    const s = catalog.find((x) => x.id === id);
    return !s || platforms.includes(s.platform); // источники снятых площадок не отправляем
  });

  const dirty =
    !!initial &&
    (query.trim() !== initial.query.trim() ||
      period[0] !== initial.period_from ||
      period[1] !== initial.period_to ||
      mode !== initial.mode ||
      !sameSet(platforms, initial.platforms) ||
      (mode === "selected" && !sameSet(sourceIds, initial.source_ids)));
  useEffect(() => onDirtyChange?.(dirty), [dirty, onDirtyChange]);

  // подсказка «как понят запрос»
  const [debounced] = useDebouncedValue(query.trim(), 800);
  const analysis = useQuery({
    queryKey: ["analyze", debounced],
    queryFn: () => unwrap(api.POST("/api/v1/query/analyze", { body: { query: debounced } })),
    enabled: debounced.length >= 3,
    retry: false,
    staleTime: Infinity,
  });

  const start = useMutation({
    mutationFn: (body: S["SearchCreateIn"]) => unwrap(api.POST("/api/v1/searches", { body })),
    onSuccess: (search) => {
      queryClient.setQueryData(["search", search.id], search);
      queryClient.invalidateQueries({ queryKey: ["searches"] });
      navigate(`/search/${search.id}`);
    },
    onError: (err) => {
      const byField: Errors = {};
      for (const [field, text] of Object.entries(fieldErrors(err))) {
        const key = SERVER_FIELD[field];
        if (key) byField[key] = text;
      }
      if (Object.keys(byField).length) setErrors(byField);
      else notifications.show({ color: "red", title: "Поиск не запущен", message: errorText(err) });
    },
  });

  function validate(): Errors {
    const e: Errors = {};
    const q = query.trim();
    if (q.length < 3) e.query = "Опишите тему, событие, человека или вставьте текст новости — хотя бы 3 символа";
    else if (q.length > 20000) e.query = "Слишком длинный текст — не больше 20 000 символов";
    const [from, to] = period;
    if (!from || !to) e.period = "Выберите начало и конец периода";
    else if (from > to) e.period = "Начало периода позже конца";
    if (platforms.length === 0) e.platforms = "Выберите хотя бы одну площадку";
    if (mode === "selected" && sourceIds.length === 0) e.sources = "Выберите хотя бы один источник";
    return e;
  }

  function submit() {
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length || start.isPending) return;
    start.mutate({
      query: query.trim(),
      period_from: period[0]!,
      period_to: period[1]!,
      mode,
      platforms,
      source_ids: mode === "selected" ? sourceIds : [],
    });
  }

  const changeSources = (ids: string[]) => {
    setSourceSel(ids);
    saveSelection(ids);
    setErrors((e) => ({ ...e, sources: undefined }));
  };

  const togglePlatform = (code: S["Platform"]) => {
    setPlatformsSel(platforms.includes(code) ? platforms.filter((p) => p !== code) : [...platforms, code]);
    setErrors((x) => ({ ...x, platforms: undefined }));
  };

  const paramErrors = [errors.period, errors.platforms, errors.sources, errors.mode].filter(Boolean);
  const allUnavailable = platformInfo.length > 0 && platformInfo.every((p) => p.status === "unavailable");
  const showAnalysis = analysis.isSuccess && debounced === query.trim();
  // «Везде» на площадках без поиска по всей площадке — там ищем только по каталогу (FE-14)
  const sourcesOnlyTitles =
    mode === "global"
      ? platformInfo
          .filter((p) => !p.global_mode && p.status !== "unavailable" && platforms.includes(p.code))
          .map((p) => PLATFORM_TITLE[p.code])
      : [];

  return (
    <form
      className={classes.hero}
      id="search-form"
      data-compact={!!initial || undefined}
      onSubmit={(ev) => {
        ev.preventDefault();
        submit();
      }}
      onKeyDown={(ev) => {
        if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
          ev.preventDefault();
          submit();
        }
      }}
    >
      <div className={classes.top}>
        <div>
          <div className={`mp-eyebrow ${classes.eyebrow}`}>
            <DataPulse compact />
            Умный поиск по смыслу
          </div>
          <h1 className={classes.title}>Что будем искать?</h1>
          {!initial && (
            <p className={classes.lead}>
              Опишите тему, событие или человека своими словами. Также можно вставить полный текст исходной новости.
            </p>
          )}
        </div>
        <PeriodButton
          preset={preset}
          period={period}
          error={!!errors.period}
          onChange={(p, value) => {
            setPreset(p);
            setPeriod(value);
            setErrors((x) => ({ ...x, period: undefined }));
          }}
        />
      </div>

      {/* 1. Запрос */}
      <div className={classes.queryBox} data-error={!!errors.query || undefined}>
        <Textarea
          variant="unstyled"
          autosize
          minRows={initial ? 2 : 3}
          maxRows={12}
          placeholder="Например: безопасность дорожного движения в Красноярском крае…"
          value={query}
          onChange={(e) => {
            setQuery(e.currentTarget.value);
            setErrors((x) => ({ ...x, query: undefined }));
          }}
          classNames={{ input: classes.queryInput }}
          aria-label="Что ищем"
          aria-invalid={!!errors.query}
        />
        <div className={classes.queryFooter}>
          <span className={classes.queryHint}>
            <Icon name="info" />
            Поиск учитывает контекст, сокращения и пересказы
          </span>
          <span className={classes.kbd}>Ctrl + Enter</span>
          <button type="submit" className="mp-ink-button" disabled={start.isPending}>
            <Icon name="search" className={start.isPending ? "mp-spin" : undefined} />
            {start.isPending ? "Ищем…" : "Найти публикации"}
          </button>
        </div>
      </div>
      {errors.query && <p className={classes.error}>{errors.query}</p>}

      {/* частые темы края — дописываются в запрос; повторный клик убирает */}
      <div className={classes.tags}>
        <span className={classes.tagsLabel}>Популярные теги</span>
        {POPULAR_TAGS.map((tag) => {
          const on = hasTag(query, tag);
          return (
            <button
              key={tag}
              type="button"
              className={`${classes.tag} ${on ? "mp-choice-pop" : ""}`}
              data-active={on || undefined}
              aria-pressed={on}
              onClick={() => {
                setQuery((q) => toggleTag(q, tag));
                setErrors((x) => ({ ...x, query: undefined }));
              }}
            >
              {tag}
            </button>
          );
        })}
      </div>

      {showAnalysis && (
        <div className={classes.analysis}>
          <div className={classes.chipRow}>
            <span className={classes.chipLabel}>Как понят запрос</span>
            <span className={`${classes.chip} ${classes.chipActive}`}>{analysis.data.query_type ? QUERY_TYPE_TEXT[analysis.data.query_type] : "Тип запроса не определён"}
            </span>
            <span className={classes.summary}>{analysis.data.summary}</span>
          </div>
          {analysis.data.search_queries.length > 0 && (
            <div className={classes.chipRow}>
              <span className={classes.chipLabel}>Ищем по формулировкам</span>
              {analysis.data.search_queries.slice(0, 8).map((q) => (
                <span key={q} className={classes.chip}>
                  {q}
                </span>
              ))}
            </div>
          )}
          {analysis.data.needs_clarification && analysis.data.clarification_hint && (
            // заметка, а не Alert: жёлто-оранжевая заливка в тёмной теме перетягивала внимание
            <p className="mp-note" style={{ margin: 0 }}>
              <Icon name="info" size={14} />
              {analysis.data.clarification_hint}
            </p>
          )}
        </div>
      )}

      {/* 2. Параметры: период · режим · площадки · источники */}
      <div className={classes.params}>
        <SegmentedControl
          size="xs"
          radius="md"
          value={mode}
          onChange={(v) => setMode(v as typeof mode)}
          data={[
            { value: "selected", label: "Мои источники" },
            { value: "global", label: "Везде" },
          ]}
          classNames={{ root: classes.segment }}
        />

        <span className={classes.divider} />

        <div className={classes.platforms} role="group" aria-label="Площадки">
          {platformInfo.map((p) => {
            const on = platforms.includes(p.code);
            const unavailable = p.status === "unavailable";
            const sourcesOnly = mode === "global" && !p.global_mode && !unavailable;
            const hints = [
              unavailable ? `${PLATFORM_NAME[p.code]} — недоступна` : PLATFORM_NAME[p.code],
              p.note ?? (unavailable ? "Площадка не подключена" : null),
              sourcesOnly ? "«Везде» здесь — все активные источники каталога" : null,
            ].filter(Boolean);
            return (
              <Tooltip key={p.code} label={hints.join(" · ")} multiline maw={280}>
                {/* aria-disabled, а не disabled: у отключённой кнопки нет событий мыши — не показалась бы подсказка с причиной */}
                <button
                  type="button"
                  className={classes.platformToggle}
                  data-on={(on && !unavailable) || undefined}
                  data-unavailable={unavailable || undefined}
                  aria-disabled={unavailable}
                  aria-pressed={on && !unavailable}
                  aria-label={hints.join(". ")}
                  onClick={() => !unavailable && togglePlatform(p.code)}
                >
                  <PlatformLogo platform={p.code} size="sm" title={null} />
                  {unavailable && (
                    <span className={classes.platformMark} data-tone="off" aria-hidden="true">
                      <Icon name="close" size={8} />
                    </span>
                  )}
                  {sourcesOnly && on && (
                    <span className={classes.platformMark} aria-hidden="true">
                      <Icon name="sources" size={8} />
                    </span>
                  )}
                </button>
              </Tooltip>
            );
          })}
        </div>

        {mode === "selected" && (
          <button type="button" className={classes.sourcesLink} onClick={picker.open}>
            {sourcesCount(sourceIds.length)} <Icon name="arrow" size={14} />
          </button>
        )}
      </div>

      {paramErrors.length > 0 && (
        <div className={classes.paramErrors}>
          {paramErrors.map((e) => (
            <p key={e} className={classes.error}>
              {e}
            </p>
          ))}
        </div>
      )}

      {sourcesOnlyTitles.length > 0 && (
        <p className={classes.modeNote}>
          <Icon name="sources" size={14} />
          {sourcesOnlyTitles.join(", ")} — только ваши источники: поиск по всей площадке не поддерживается
        </p>
      )}

      {/* без ключей (COLLECTOR_FAKE=false) все площадки unavailable — объясняем, почему искать негде */}
      {allUnavailable && (
        <p className={classes.warning}>
          Сейчас ни одна площадка не подключена, поиск недоступен. Причина — в подсказке у логотипа площадки.
        </p>
      )}

      {/* 3. Источники */}
      {mode === "selected" && (
        <SourcePicker
          value={sourceIds}
          onChange={changeSources}
          platforms={platforms}
          catalog={catalog}
          error={errors.sources}
          opened={pickerOpened}
          onOpen={picker.open}
          onClose={picker.close}
        />
      )}
    </form>
  );
}

/** Кнопка периода в углу формы (макет v2): быстрые периоды, календарь на диапазон и «Применить период». */
function PeriodButton({
  preset,
  period,
  error,
  onChange,
}: {
  preset: PeriodPreset;
  period: Period;
  error: boolean;
  onChange: (preset: PeriodPreset, period: Period) => void;
}) {
  const [opened, setOpened] = useState(false);
  const [draft, setDraft] = useState<Period>(period);
  useEffect(() => {
    if (opened) setDraft(period);
  }, [opened]); // eslint-disable-line react-hooks/exhaustive-deps -- черновик берём при открытии

  return (
    <Popover
      opened={opened}
      onChange={setOpened}
      position="bottom-end"
      shadow="xl"
      radius="lg"
      withinPortal
      transitionProps={{ transition: "pop-top-right", duration: 200 }}
    >
      <Popover.Target>
        <button
          type="button"
          className={`${classes.periodButton} mp-press`}
          data-error={error || undefined}
          aria-expanded={opened}
          aria-label={`Период публикации: ${periodLabel(preset, period)}`}
          onClick={() => setOpened((x) => !x)}
        >
          <Icon name="calendar" />
          {periodLabel(preset, period)}
          <Icon name="chevron" size={14} className={opened ? classes.flip : undefined} />
        </button>
      </Popover.Target>
      <Popover.Dropdown p="sm" className={classes.periodDropdown}>
        <p className={classes.periodCaption}>Быстрый период</p>
        <div className={classes.presetGrid}>
          {PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              className={classes.preset}
              data-active={preset === p.value || undefined}
              onClick={() => {
                onChange(p.value, presetPeriod(p.value));
                setOpened(false);
              }}
            >
              {p.short}
            </button>
          ))}
        </div>
        <div className={classes.periodDates}>
          <p className={classes.periodCaption}>Выбрать даты</p>
          <DatesProvider settings={{ locale: "ru", firstDayOfWeek: 1 }}>
            <DatePicker
              type="range"
              size="xs"
              value={draft}
              onChange={(v) => setDraft([v[0], v[1]])}
              maxDate={todayYmd()}
              allowSingleDateInRange
              defaultDate={draft[1] ?? undefined}
            />
          </DatesProvider>
          <button
            type="button"
            className={classes.applyPeriod}
            disabled={!draft[0] || !draft[1]}
            onClick={() => {
              onChange(detectPreset(draft), draft);
              setOpened(false);
            }}
          >
            Применить период
          </button>
        </div>
      </Popover.Dropdown>
    </Popover>
  );
}
