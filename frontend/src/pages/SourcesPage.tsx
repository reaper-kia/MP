// Управление источниками (FE-08): таблица с поиском и фильтром, переключатели, заметки, добавление, удаление.
// Импорт из Excel спрятан, пока бэкенд отвечает 501 (B2-10).
import {
  ActionIcon,
  Alert,
  Anchor,
  Button,
  Group,
  Modal,
  Pagination,
  SegmentedControl,
  Skeleton,
  Switch,
  Table,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import type { S } from "../api/client";
import { Icon } from "../components/Icon";
import { PlatformLogo } from "../components/PlatformLogo";
import { useAllSources, usePlatforms } from "../features/search/useCatalog";
import { AddSource } from "../features/sources/AddSource";
import { SOURCES_PAGE, useDeleteSource, useSourcePage, useUpdateSource } from "../features/sources/useSources";
import { errorText } from "../lib/errors";
import { sourcesCount } from "../lib/format";
import { PLATFORM_NAME } from "../lib/platforms";
import classes from "./SourcesPage.module.css";

const PLATFORM_FILTER = [
  { value: "all", label: "Все площадки" },
  { value: "vk", label: "VK" },
  { value: "ok", label: "OK" },
  { value: "max", label: "MAX" },
  { value: "news", label: "Новости" },
];

export function SourcesPage() {
  const [q, setQ] = useState("");
  const [debouncedQ] = useDebouncedValue(q.trim(), 300);
  const [platform, setPlatform] = useState<S["Platform"] | null>(null);
  const [page, setPage] = useState(1);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<S["Source"] | null>(null);

  // Сменили фильтр — на первую страницу
  useEffect(() => setPage(1), [debouncedQ, platform]);

  const sources = useSourcePage({ q: debouncedQ, platform, page });
  const update = useUpdateSource();
  const data = sources.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / SOURCES_PAGE)) : 1;

  // После удаления последней строки страницы — на предыдущую
  useEffect(() => {
    if (data && page > pages) setPage(pages);
  }, [data, page, pages]);

  // Подсвеченная строка («Уже в списке» → «Показать в таблице») — прокрутить к ней
  useEffect(() => {
    if (!highlight || !data?.items.some((s) => s.id === highlight)) return;
    document.getElementById(`source-${highlight}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlight, data]);

  const showExisting = (p: S["SourcePreview"]) => {
    setQ(p.name);
    setPlatform(p.platform);
    setHighlight(p.existing_source_id);
  };

  // Добавили — снимаем фильтры, чтобы новая строка была видна, и подсвечиваем её
  const showAdded = (s: S["Source"]) => {
    setQ("");
    setPlatform(null);
    setHighlight(s.id);
  };

  return (
    <div className={`mp-container ${classes.page}`}>
      <div>
        <h1 className="mp-page-title">Источники</h1>
        <p className="mp-page-lead">Управляйте группами, сообществами и каналами без изменения настроек системы.</p>
      </div>

      <PlatformStats />

      <AddSource onShowExisting={showExisting} onAdded={showAdded} />

      <Group gap="sm" wrap="wrap">
        <TextInput
          placeholder="Поиск по названию или ссылке"
          leftSection={<Icon name="search" />}
          value={q}
          onChange={(e) => setQ(e.currentTarget.value)}
          w={320}
          aria-label="Поиск по источникам"
        />
        <SegmentedControl
          value={platform ?? "all"}
          onChange={(v) => setPlatform(v === "all" ? null : (v as S["Platform"]))}
          data={PLATFORM_FILTER}
        />
        {data && (
          <Text size="sm" c="dimmed" ml="auto">
            {debouncedQ || platform ? `Найдено: ${sourcesCount(data.total)}` : `Всего: ${sourcesCount(data.total)}`}
          </Text>
        )}
      </Group>

      {sources.isError && !data && (
        <Alert color="red" title="Не удалось загрузить источники">
          {errorText(sources.error)}{" "}
          <Anchor component="button" type="button" size="sm" onClick={() => sources.refetch()}>
            Повторить
          </Anchor>
        </Alert>
      )}

      <div className={classes.tableCard}>
      <Table
        highlightOnHover
        verticalSpacing="sm"
        horizontalSpacing="md"
        classNames={{ th: classes.th, tr: classes.tr }}
        style={{ opacity: sources.isPlaceholderData ? 0.6 : 1 }}
      >
        <Table.Thead>
          <Table.Tr>
            <Table.Th w={70}>Площадка</Table.Th>
            <Table.Th>Название</Table.Th>
            <Table.Th w={140}>Город</Table.Th>
            <Table.Th w={120}>Региональный</Table.Th>
            <Table.Th w={150}>
              Активный
              <Text size="xs" c="dimmed" fw={400} tt="none" lts={0}>
                участвует в поиске «Везде»
              </Text>
            </Table.Th>
            <Table.Th>Заметка</Table.Th>
            <Table.Th w={60} />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {sources.isPending &&
            [0, 1, 2, 3].map((i) => (
              <Table.Tr key={i}>
                <Table.Td colSpan={7}>
                  <Skeleton height={14} />
                </Table.Td>
              </Table.Tr>
            ))}
          {data?.items.map((s) => (
            <Table.Tr
              key={s.id}
              id={`source-${s.id}`}
              bg={s.id === highlight ? "var(--mp-accent-soft)" : undefined}
            >
              <Table.Td>
                <PlatformLogo platform={s.platform} size="sm" />
              </Table.Td>
              <Table.Td>
                <Anchor href={s.url} target="_blank" rel="noopener noreferrer" size="sm" fw={700} c="var(--mp-text)">
                  {s.name}
                </Anchor>
              </Table.Td>
              <Table.Td>
                <Text size="sm">{s.city ?? "—"}</Text>
              </Table.Td>
              <Table.Td>
                <Switch
                  checked={s.is_regional}
                  onChange={(e) => update.mutate({ id: s.id, patch: { is_regional: e.currentTarget.checked } })}
                  aria-label={`Региональный: ${s.name}`}
                />
              </Table.Td>
              <Table.Td>
                <Switch
                  checked={s.is_active}
                  onChange={(e) => update.mutate({ id: s.id, patch: { is_active: e.currentTarget.checked } })}
                  aria-label={`Активный: ${s.name}`}
                />
              </Table.Td>
              <Table.Td>
                <NoteCell source={s} onSave={(notes) => update.mutate({ id: s.id, patch: { notes } })} />
              </Table.Td>
              <Table.Td>
                <Tooltip label="Удалить источник">
                  <ActionIcon variant="subtle" color="red" onClick={() => setToDelete(s)} aria-label={`Удалить ${s.name}`}>
                    <Icon name="trash" />
                  </ActionIcon>
                </Tooltip>
              </Table.Td>
            </Table.Tr>
          ))}
          {data && data.items.length === 0 && (
            <Table.Tr>
              <Table.Td colSpan={7}>
                <Text c="dimmed" ta="center" py="md">
                  {debouncedQ || platform
                    ? "Под эти условия источников нет."
                    : "Список пуст — добавьте первый источник по ссылке выше."}
                </Text>
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>
      </div>

      {pages > 1 && (
        <Group justify="center">
          <Pagination value={page} onChange={setPage} total={pages} />
        </Group>
      )}

      <DeleteModal source={toDelete} onClose={() => setToDelete(null)} />
    </div>
  );
}

const STATUS_VIEW: Record<S["PlatformInfo"]["status"], { label: string; color: string; fill: number }> = {
  ok: { label: "Работает", color: "#34d399", fill: 100 },
  degraded: { label: "Работает с ограничениями", color: "#fbbf24", fill: 60 },
  unavailable: { label: "Не подключена", color: "#f87171", fill: 8 },
};

/** Карточки площадок из макета: сколько источников в каталоге и состояние площадки из GET /platforms. */
function PlatformStats() {
  const platforms = usePlatforms();
  const all = useAllSources();
  const list = platforms.data ?? [];
  if (list.length === 0) return null;
  const items = all.data?.items ?? [];

  return (
    <div className={classes.stats}>
      {list.map((p) => {
        const n = items.filter((s) => s.platform === p.code).length;
        const active = items.filter((s) => s.platform === p.code && s.is_active).length;
        const st = STATUS_VIEW[p.status];
        return (
          <Tooltip
            key={p.code}
            label={p.note ?? (p.status === "unavailable" ? "Площадка не подключена" : "")}
            disabled={!p.note && p.status !== "unavailable"}
            multiline
            maw={280}
          >
            <div className={classes.stat}>
              <div className={classes.statHead}>
                <PlatformLogo platform={p.code} title={null} />
                <div>
                  <p className={classes.statName}>{PLATFORM_NAME[p.code]}</p>
                  <p className={classes.statMeta}>
                    {all.isSuccess ? `${sourcesCount(n)} · активных ${active}` : "…"}
                  </p>
                </div>
              </div>
              <div className={classes.bar}>
                <div style={{ width: `${st.fill}%`, background: st.color }} />
              </div>
              <p className={classes.statStatus}>
                {st.label}
                {p.global_mode ? " · поиск «Везде»" : " · только по списку"}
              </p>
            </div>
          </Tooltip>
        );
      })}
    </div>
  );
}

/** Заметка: текст, по клику — поле; Enter / уход с поля — сохранить, Esc — отменить. */
function NoteCell({ source, onSave }: { source: S["Source"]; onSave: (notes: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(source.notes);
  useEffect(() => setValue(source.notes), [source.notes]);

  const save = () => {
    setEditing(false);
    if (value.trim() !== source.notes) onSave(value.trim());
  };

  if (editing) {
    return (
      <TextInput
        size="xs"
        autoFocus
        value={value}
        maxLength={1000}
        onChange={(e) => setValue(e.currentTarget.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") {
            setValue(source.notes);
            setEditing(false);
          }
        }}
        aria-label={`Заметка: ${source.name}`}
      />
    );
  }
  return (
    <Anchor component="button" type="button" size="sm" c={source.notes ? undefined : "dimmed"} onClick={() => setEditing(true)} ta="left">
      {source.notes || "+ заметка"}
    </Anchor>
  );
}

function DeleteModal({ source, onClose }: { source: S["Source"] | null; onClose: () => void }) {
  const del = useDeleteSource();
  // имя держим, пока модалка закрывается с анимацией
  const [name, setName] = useState("");
  useEffect(() => {
    if (source) setName(source.name);
  }, [source]);

  const confirm = () => {
    if (!source) return;
    del.mutate(source.id, {
      onSuccess: () => {
        notifications.show({ color: "gray", title: "Источник удалён", message: `«${source.name}» больше не участвует в поиске` });
        onClose();
      },
      onError: (err) => notifications.show({ color: "red", title: "Не удалось удалить", message: errorText(err, "source") }),
    });
  };

  return (
    <Modal opened={!!source} onClose={onClose} title={`Удалить «${name}»?`} centered>
      <Text size="sm">Источник пропадёт из списка и из новых поисков. История прошлых поисков сохранится.</Text>
      <Group justify="flex-end" mt="lg">
        <Button variant="default" onClick={onClose}>
          Отмена
        </Button>
        <Button color="red" loading={del.isPending} onClick={confirm}>
          Удалить
        </Button>
      </Group>
    </Modal>
  );
}

