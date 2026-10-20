// Источники по макету v2: карточки площадок, под ними — раскрывающиеся блоки с карточками сообществ.
// Отметка на карточке = «активный» (участвует в поиске «Везде» и выбран по умолчанию) — PATCH is_active.
// В макете сообщества «загружаются» из аккаунта соцсети; у нас входа нет (контракт: все ручки анонимные),
// поэтому каталог наполняется по ссылке (AddSource), а кнопка площадки просто раскрывает её блок.
import { Button, Group, Modal, Skeleton, Text, TextInput, Tooltip } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import type { S } from "../api/client";
import { Icon } from "../components/Icon";
import { PlatformLogo } from "../components/PlatformLogo";
import { SourceStack } from "../components/Signal";
import { useAllSources, usePlatforms } from "../features/search/useCatalog";
import { AddSource } from "../features/sources/AddSource";
import { useDeleteSource, usePlatformSources, useUpdateSource } from "../features/sources/useSources";
import { errorText } from "../lib/errors";
import { fmtNumber, sourcesCount } from "../lib/format";
import { PLATFORM_NAME } from "../lib/platforms";
import classes from "./SourcesPage.module.css";

const STATUS_VIEW: Record<S["PlatformInfo"]["status"], { label: string; color: string }> = {
  ok: { label: "Работает", color: "#34d399" },
  degraded: { label: "С ограничениями", color: "#fbbf24" },
  unavailable: { label: "Не подключена", color: "#f87171" },
};

const host = (url: string) => {
  try {
    return new URL(url).host.replace(/^www\./, "") + new URL(url).pathname.replace(/\/$/, "");
  } catch {
    return url;
  }
};

export function SourcesPage() {
  const platforms = usePlatforms();
  const all = useAllSources();
  const [q, setQ] = useState("");
  const [debouncedQ] = useDebouncedValue(q.trim(), 300);
  // раскрытые блоки площадок; null — «как по умолчанию»: раскрыты все, где есть источники
  const [expanded, setExpanded] = useState<S["Platform"][] | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<S["Source"] | null>(null);
  // ?add=<ссылка> — расширение Chrome (FE-10) прислало адрес открытой вкладки: сразу проверяем его
  const [params] = useSearchParams();
  const addUrl = params.get("add") ?? undefined;

  const list = platforms.data ?? [];
  const items = all.data?.items ?? [];
  const activeCount = items.filter((s) => s.is_active).length;
  const withSources = list.filter((p) => items.some((s) => s.platform === p.code)).map((p) => p.code);
  const open = expanded ?? withSources;
  // ищем по всем площадкам — блоки, где могут быть совпадения, раскрыты
  const shown = debouncedQ ? list.map((p) => p.code) : open;

  const toggle = (code: S["Platform"]) =>
    setExpanded(open.includes(code) ? open.filter((c) => c !== code) : [...open, code]);

  const reveal = (id: string, platform: S["Platform"], name: string) => {
    setQ(name);
    setExpanded([...new Set([...open, platform])]);
    setHighlight(id);
  };

  // Подсвеченная карточка («Уже в списке» → «Показать», только что добавленная) — прокрутить к ней
  useEffect(() => {
    if (!highlight) return;
    const timer = window.setTimeout(
      () => document.getElementById(`source-${highlight}`)?.scrollIntoView({ block: "center", behavior: "smooth" }),
      350,
    );
    return () => window.clearTimeout(timer);
  }, [highlight, debouncedQ]);

  return (
    <div className={`mp-container mp-page-enter ${classes.page}`}>
      <div className={classes.head}>
        <div>
          <h1 className="mp-page-title">Источники</h1>
          <p className="mp-page-lead">
            Добавьте группы, сообщества, каналы и сайты по ссылке и отметьте те, публикации которых должны попадать в
            поиск по умолчанию.
          </p>
        </div>
        <div className={`${classes.counter} mp-signal-counter`}>
          <p className={classes.counterLabel}>Выбрано</p>
          <p className={classes.counterValue}>
            <SourceStack />
            {all.isSuccess ? `${fmtNumber(activeCount)} из ${fmtNumber(all.data.total)}` : "…"}
          </p>
        </div>
      </div>

      <div className={`${classes.platforms} mp-stagger`}>
        {list.map((p) => {
          const n = items.filter((s) => s.platform === p.code).length;
          const active = items.filter((s) => s.platform === p.code && s.is_active).length;
          const st = STATUS_VIEW[p.status];
          const isOpen = open.includes(p.code);
          return (
            <div key={p.code} className={`${classes.platform} mp-signal-card mp-motion-card`}>
              <div className={classes.platformHead}>
                <PlatformLogo platform={p.code} title={null} />
                <div className={classes.platformText}>
                  <p className={classes.platformName}>{PLATFORM_NAME[p.code]}</p>
                  <p className={classes.platformMeta}>
                    {all.isSuccess ? (n ? `${active} из ${n} выбрано` : "Источников пока нет") : "…"}
                  </p>
                </div>
              </div>
              <Tooltip label={p.note ?? ""} disabled={!p.note} multiline maw={280}>
                <p className={classes.platformStatus}>
                  <span className="mp-dot" style={{ background: st.color }} />
                  {st.label}
                  {p.global_mode ? " · поиск «Везде»" : " · только по списку"}
                </p>
              </Tooltip>
              <button
                type="button"
                className={`${classes.platformButton} mp-press`}
                data-open={isOpen || undefined}
                disabled={n === 0}
                onClick={() => toggle(p.code)}
                aria-expanded={isOpen}
              >
                <Icon name={isOpen ? "check" : n === 0 ? "plus" : "sources"} size={14} />
                {n === 0 ? "Нет источников" : isOpen ? "Скрыть сообщества" : "Показать сообщества"}
              </button>
            </div>
          );
        })}
        {platforms.isPending &&
          [0, 1, 2].map((i) => (
            <div key={i} className={classes.platform}>
              <Skeleton height={40} width={40} radius="md" mb="md" />
              <Skeleton height={12} width="60%" />
            </div>
          ))}
      </div>

      <AddSource
        key={addUrl}
        initialUrl={addUrl}
        onShowExisting={(p) => p.existing_source_id && reveal(p.existing_source_id, p.platform, p.name)}
        onAdded={(s) => reveal(s.id, s.platform, "")}
      />

      <div className={classes.listHead}>
        <div>
          <h2 className={classes.listTitle}>Доступные сообщества</h2>
          <p className={classes.listHint}>Нажмите на карточку, чтобы включить или исключить источник из поиска по умолчанию.</p>
        </div>
        <TextInput
          placeholder="Поиск по названию или ссылке"
          leftSection={<Icon name="search" />}
          value={q}
          onChange={(e) => setQ(e.currentTarget.value)}
          w={300}
          radius="md"
          aria-label="Поиск по источникам"
        />
      </div>

      {all.isSuccess && items.length === 0 && !debouncedQ ? (
        <div className={classes.empty}>
          <span className={classes.emptyIcon}>
            <Icon name="sources" size={20} />
          </span>
          <p className={classes.emptyTitle}>Подключите первый источник</p>
          <p className={classes.emptyText}>Вставьте ссылку на группу VK, Одноклассников, канал MAX или сайт — он появится здесь.</p>
        </div>
      ) : (
        <div className={`${classes.sections} mp-stagger`}>
          {list
            .filter((p) => shown.includes(p.code))
            .map((p) => (
              <PlatformSection
                key={p.code}
                platform={p.code}
                q={debouncedQ}
                expanded={open.includes(p.code) || !!debouncedQ}
                onToggle={() => toggle(p.code)}
                highlight={highlight}
                onDelete={setToDelete}
              />
            ))}
        </div>
      )}

      <DeleteModal source={toDelete} onClose={() => setToDelete(null)} />
    </div>
  );
}

function PlatformSection({
  platform,
  q,
  expanded,
  onToggle,
  highlight,
  onDelete,
}: {
  platform: S["Platform"];
  q: string;
  expanded: boolean;
  onToggle: () => void;
  highlight: string | null;
  onDelete: (s: S["Source"]) => void;
}) {
  const sources = usePlatformSources(platform, q, true);
  const update = useUpdateSource();
  const pages = sources.data?.pages ?? [];
  const items = pages.flatMap((p) => p.items);
  const total = pages[0]?.total ?? 0;
  const active = items.filter((s) => s.is_active).length;

  // при поиске пустые площадки не показываем
  if (q && sources.isSuccess && total === 0) return null;

  return (
    <section className={`${classes.section} mp-motion-card`} data-lift="soft">
      <button type="button" className={classes.sectionHead} onClick={onToggle} aria-expanded={expanded}>
        <PlatformLogo platform={platform} size="sm" title={null} />
        <span className={classes.sectionText}>
          <span className={classes.sectionName}>{PLATFORM_NAME[platform]}</span>
          <span className={classes.sectionMeta}>
            {sources.isSuccess
              ? q
                ? `Найдено: ${sourcesCount(total)}`
                : `${active} из ${total} выбрано`
              : "Загружаем…"}
          </span>
        </span>
        <span className={classes.sectionToggle}>{expanded ? "Свернуть" : "Показать"}</span>
        <Icon name="chevron" className={expanded ? classes.flip : undefined} />
      </button>

      {expanded && (
        <div className={`${classes.grid} mp-accordion-in`}>
          {sources.isError && !sources.data && (
            <p className={classes.error}>
              {errorText(sources.error)}{" "}
              <button type="button" className={classes.link} onClick={() => sources.refetch()}>
                Повторить
              </button>
            </p>
          )}
          {sources.isPending &&
            [0, 1].map((i) => (
              <div key={i} className={classes.community}>
                <Skeleton height={40} width={40} radius="md" />
                <Skeleton height={12} width="60%" />
              </div>
            ))}
          {items.map((s) => (
            <CommunityCard
              key={s.id}
              source={s}
              highlighted={s.id === highlight}
              onToggleActive={() => update.mutate({ id: s.id, patch: { is_active: !s.is_active } })}
              onToggleRegional={() => update.mutate({ id: s.id, patch: { is_regional: !s.is_regional } })}
              onSaveNote={(notes) => update.mutate({ id: s.id, patch: { notes } })}
              onDelete={() => onDelete(s)}
            />
          ))}
          {sources.hasNextPage && (
            <Group justify="center" className={classes.more}>
              <Button variant="default" size="xs" loading={sources.isFetchingNextPage} onClick={() => sources.fetchNextPage()}>
                Показать ещё
              </Button>
            </Group>
          )}
        </div>
      )}
    </section>
  );
}

function CommunityCard({
  source: s,
  highlighted,
  onToggleActive,
  onToggleRegional,
  onSaveNote,
  onDelete,
}: {
  source: S["Source"];
  highlighted: boolean;
  onToggleActive: () => void;
  onToggleRegional: () => void;
  onSaveNote: (notes: string) => void;
  onDelete: () => void;
}) {
  return (
    <div
      id={`source-${s.id}`}
      className={classes.community}
      data-selected={s.is_active || undefined}
      data-highlight={highlighted || undefined}
    >
      <button
        type="button"
        role="checkbox"
        aria-checked={s.is_active}
        className={classes.communityMain}
        onClick={onToggleActive}
        title={s.is_active ? "Исключить из поиска по умолчанию" : "Включить в поиск по умолчанию"}
      >
        <PlatformLogo platform={s.platform} title={null} />
        <span className={classes.communityText}>
          <span className={classes.communityName}>
            <span className={classes.truncate}>{s.name}</span>
            {s.is_regional && <Icon name="check" size={14} className={classes.regionalMark} />}
          </span>
          <span className={classes.communityMeta}>
            {[s.city, host(s.url)].filter(Boolean).join(" · ")}
          </span>
        </span>
        <span className={classes.checkbox} data-on={s.is_active || undefined} aria-hidden="true">
          <Icon name="check" size={14} />
        </span>
      </button>
      <div className={classes.communityActions}>
        <button
          type="button"
          className={classes.chip}
          data-on={s.is_regional || undefined}
          aria-pressed={s.is_regional}
          onClick={onToggleRegional}
          title="Источник относится к Красноярскому краю"
        >
          <Icon name="location" size={12} />
          {s.is_regional ? "Региональный" : "Не региональный"}
        </button>
        <NoteButton source={s} onSave={onSaveNote} />
        <a href={s.url} target="_blank" rel="noopener noreferrer" className={classes.iconAction} aria-label={`Открыть ${s.name}`}>
          <Icon name="external" size={14} />
        </a>
        <button type="button" className={`${classes.iconAction} ${classes.danger}`} onClick={onDelete} aria-label={`Удалить ${s.name}`}>
          <Icon name="trash" size={14} />
        </button>
      </div>
    </div>
  );
}

/** Заметка: текст, по клику — поле; Enter / уход с поля — сохранить, Esc — отменить. */
function NoteButton({ source, onSave }: { source: S["Source"]; onSave: (notes: string) => void }) {
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
        className={classes.noteInput}
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
    <button type="button" className={classes.note} data-empty={!source.notes || undefined} onClick={() => setEditing(true)} title={source.notes || undefined}>
      {source.notes || "+ заметка"}
    </button>
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
