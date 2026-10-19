import {
  Alert,
  Box,
  Button,
  Checkbox,
  Group,
  Kbd,
  Paper,
  SegmentedControl,
  Stack,
  Text,
  Textarea,
  Tooltip,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";

import { api, unwrap, type S } from "../../api/client";
import { errorText, fieldErrors } from "../../lib/errors";
import { todayYmd } from "../../lib/dates";
import { detectPreset, presetPeriod, type Period, type PeriodPreset } from "./period";
import { loadSelection, saveSelection } from "./sourceSelection";
import { SourcePicker } from "./SourcePicker";
import { useAllSources, usePlatforms } from "./useCatalog";

const QUERY_TYPE_TEXT: Record<S["QueryType"], string> = {
  topic: "тема",
  event: "событие",
  person: "человек",
  news_text: "текст новости — ищем её размещения",
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
}

export function SearchForm({ initial }: Props) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const platformsQ = usePlatforms();
  const sourcesQ = useAllSources();

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
    if (q.length < 3) e.query = "Опишите, что ищем, — хотя бы 3 символа";
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

  return (
    <Paper
      withBorder
      p="md"
      radius="md"
      component="form"
      onSubmit={(ev: React.FormEvent) => {
        ev.preventDefault();
        submit();
      }}
      onKeyDown={(ev: React.KeyboardEvent) => {
        if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
          ev.preventDefault();
          submit();
        }
      }}
    >
      <Stack gap="md">
        {/* 1. Запрос */}
        <Box>
          <Textarea
            label="Что ищем?"
            description="Тема, событие, человек или текст новости целиком"
            placeholder="Например: безопасность дорожного движения в Красноярском крае"
            autosize
            minRows={2}
            maxRows={12}
            value={query}
            onChange={(e) => {
              setQuery(e.currentTarget.value);
              setErrors((x) => ({ ...x, query: undefined }));
            }}
            error={errors.query}
          />
          {analysis.isSuccess && debounced === query.trim() && (
            <Stack gap={4} mt={6}>
              <Text size="sm" c="dimmed">
                Понято как: <b>{QUERY_TYPE_TEXT[analysis.data.query_type]}</b> — {analysis.data.summary}
              </Text>
              {analysis.data.needs_clarification && analysis.data.clarification_hint && (
                <Alert color="yellow" variant="light" p="xs">
                  {analysis.data.clarification_hint}
                </Alert>
              )}
            </Stack>
          )}
        </Box>

        {/* 2. Период и режим */}
        <Group align="flex-start" gap="xl" wrap="wrap">
          <Stack gap={6}>
            <Text size="sm" fw={500}>
              Период{" "}
              <Text span size="xs" c="dimmed" fw={400}>
                по дате публикации
              </Text>
            </Text>
            <SegmentedControl
              value={preset}
              onChange={(v) => {
                const p = v as PeriodPreset;
                setPreset(p);
                if (p !== "custom") setPeriod(presetPeriod(p));
                setErrors((x) => ({ ...x, period: undefined }));
              }}
              data={[
                { value: "today", label: "Сегодня" },
                { value: "7d", label: "7 дней" },
                { value: "30d", label: "30 дней" },
                { value: "custom", label: "Свой" },
              ]}
            />
            <DatePickerInput
              type="range"
              value={period}
              onChange={(v) => {
                setPeriod([v[0], v[1]]);
                setPreset("custom");
                setErrors((x) => ({ ...x, period: undefined }));
              }}
              maxDate={todayYmd()}
              allowSingleDateInRange
              valueFormat="DD.MM.YYYY"
              placeholder="Выберите даты"
              error={errors.period}
              w={260}
            />
          </Stack>

          <Stack gap={6}>
            <Text size="sm" fw={500}>
              Где искать
            </Text>
            <SegmentedControl
              value={mode}
              onChange={(v) => setMode(v as typeof mode)}
              data={[
                { value: "selected", label: "Только мои источники" },
                { value: "global", label: "Везде" },
              ]}
            />
            <Checkbox.Group
              value={platforms}
              onChange={(v) => {
                setPlatformsSel(v as S["Platform"][]);
                setErrors((x) => ({ ...x, platforms: undefined }));
              }}
              error={errors.platforms}
            >
              <Group gap="md" mt={4}>
                {platformInfo.map((p) => {
                  const box = (
                    <Checkbox
                      value={p.code}
                      label={p.title}
                      disabled={p.status === "unavailable"}
                      description={
                        mode === "global" && !p.global_mode ? "здесь — только по источникам из списка" : undefined
                      }
                    />
                  );
                  return p.note ? (
                    <Tooltip key={p.code} label={p.note} multiline w={240}>
                      <div>{box}</div>
                    </Tooltip>
                  ) : (
                    <div key={p.code}>{box}</div>
                  );
                })}
              </Group>
            </Checkbox.Group>
          </Stack>
        </Group>

        {/* 3. Источники */}
        {mode === "selected" && (
          <Stack gap={4}>
            <Text size="sm" fw={500}>
              Источники
            </Text>
            <SourcePicker
              value={sourceIds}
              onChange={changeSources}
              platforms={platforms}
              catalog={catalog}
              error={errors.sources}
            />
          </Stack>
        )}

        <Group justify="space-between" wrap="wrap">
          <Group gap={6}>
            <Text size="sm" c="dimmed">
              Регион: Красноярский край
            </Text>
            <Tooltip
              multiline
              w={300}
              label="Публикация попадает в подборку, если она из регионального источника или в тексте упоминается край (город, район)"
            >
              <Text size="sm" c="dimmed" style={{ cursor: "help" }}>
                ⓘ
              </Text>
            </Tooltip>
          </Group>
          <Group gap="sm">
            <Text size="xs" c="dimmed">
              <Kbd size="xs">Ctrl</Kbd> + <Kbd size="xs">Enter</Kbd>
            </Text>
            <Button type="submit" loading={start.isPending} size="md">
              Найти
            </Button>
          </Group>
        </Group>
      </Stack>
    </Paper>
  );
}
