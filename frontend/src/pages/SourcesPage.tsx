// Управление источниками (FE-08): таблица с поиском и фильтром, переключатели, заметки, добавление, удаление.
// Импорт из Excel спрятан, пока бэкенд отвечает 501 (B2-10).
import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Group,
  Modal,
  Pagination,
  SegmentedControl,
  Skeleton,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";

import type { S } from "../api/client";
import { AddSource } from "../features/sources/AddSource";
import { SOURCES_PAGE, useDeleteSource, useSourcePage, useUpdateSource } from "../features/sources/useSources";
import { errorText } from "../lib/errors";
import { sourcesCount } from "../lib/format";
import { PLATFORM_TITLE } from "../lib/platforms";

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
    <Stack>
      <Title order={2}>Источники</Title>
      <AddSource onShowExisting={showExisting} onAdded={showAdded} />

      <Group gap="sm" wrap="wrap">
        <TextInput
          placeholder="Поиск по названию или ссылке"
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

      <Table striped highlightOnHover verticalSpacing="xs" style={{ opacity: sources.isPlaceholderData ? 0.6 : 1 }}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th w={80}>Площадка</Table.Th>
            <Table.Th>Название</Table.Th>
            <Table.Th w={140}>Город</Table.Th>
            <Table.Th w={120}>Региональный</Table.Th>
            <Table.Th w={150}>
              Активный
              <Text size="xs" c="dimmed" fw={400}>
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
              bg={s.id === highlight ? "var(--mantine-color-yellow-light)" : undefined}
            >
              <Table.Td>
                <Badge variant="outline" color="gray">
                  {PLATFORM_TITLE[s.platform]}
                </Badge>
              </Table.Td>
              <Table.Td>
                <Anchor href={s.url} target="_blank" rel="noopener noreferrer" size="sm">
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
                    ✕
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

      {pages > 1 && (
        <Group justify="center">
          <Pagination value={page} onChange={setPage} total={pages} />
        </Group>
      )}

      <DeleteModal source={toDelete} onClose={() => setToDelete(null)} />
    </Stack>
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

