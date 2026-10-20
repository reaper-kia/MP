import { Accordion, Anchor, Button, Text, UnstyledButton } from "@mantine/core";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";

import type { S } from "../../api/client";
import { Icon } from "../../components/Icon";
import { PlatformLogo } from "../../components/PlatformLogo";
import { isFinal, TARGET_STATUS } from "./status";
import classes from "./TargetsPanel.module.css";
import { useRetry } from "./useSearch";

const ITEM = "targets";

const DOT: Record<S["TargetStatus"], string> = {
  pending: "#c5c9ba",
  running: "#60a5fa",
  done: "#34d399",
  empty: "#979b8d",
  failed: "#f87171",
  skipped: "#c5c9ba",
};

/** «Где искали»: раскрыт во время поиска, после финала сворачивается в строку-итог. */
export function TargetsPanel({ search }: { search: S["Search"] }) {
  const final = isFinal(search.status);
  const [open, setOpen] = useState<string | null>(final ? null : ITEM);
  const wasFinal = useRef(final);
  useEffect(() => {
    if (final && !wasFinal.current) setOpen(null); // поиск только что закончился — свернуть
    if (!final && wasFinal.current) setOpen(ITEM); // повтор запустил поиск заново — раскрыть
    wasFinal.current = final;
  }, [final]);

  // Клик по строке цели — фильтр подборки target_id (FE-05), повторный клик снимает
  const [params, setParams] = useSearchParams();
  const activeTargets = params.getAll("target_id");
  const toggleTarget = (id: string) => {
    const next = new URLSearchParams(params);
    next.delete("target_id");
    if (!activeTargets.includes(id)) next.append("target_id", id);
    setParams(next, { replace: true });
  };

  const retry = useRetry(search.id);
  const count = (st: S["TargetStatus"]) => search.targets.filter((t) => t.status === st).length;
  const failed = count("failed");
  const processed = count("done") + count("empty");

  return (
    <Accordion
      variant="contained"
      radius="lg"
      value={open}
      onChange={setOpen}
      classNames={{ item: classes.item, control: classes.control, panel: classes.panel }}
    >
      <Accordion.Item value={ITEM}>
        <Accordion.Control icon={<Icon name="sources" className={classes.controlIcon} />}>
          <span className={classes.head}>
            <span className={classes.headTitle}>Где искали</span>
            <span className={classes.headMeta}>
              Обработано {processed} из {search.targets.length}
              {failed > 0 && <span className={classes.headFailed}> · не удалось: {failed}</span>}
              {activeTargets.length > 0 && " · подборка отфильтрована по источнику"}
            </span>
          </span>
        </Accordion.Control>
        <Accordion.Panel>
          {final && failed > 0 && (
            <Button
              size="compact-sm"
              variant="light"
              mb="xs"
              leftSection={<Icon name="refresh" size={14} />}
              loading={retry.isPending}
              onClick={() => retry.mutate(undefined)}
            >
              Повторить все неудачные
            </Button>
          )}
          {search.targets.length === 0 && (
            <Text size="sm" c="dimmed">
              Список источников появится, когда поиск начнётся.
            </Text>
          )}
          <div className={classes.list}>
            {search.targets.map((t) => (
              <TargetRow
                key={t.id}
                target={t}
                active={activeTargets.includes(t.id)}
                onToggle={() => toggleTarget(t.id)}
                onRetry={() => retry.mutate([t.id])}
                retrying={retry.isPending && retry.variables?.includes(t.id) === true}
              />
            ))}
          </div>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}

interface RowProps {
  target: S["SearchTarget"];
  active: boolean;
  onToggle: () => void;
  onRetry: () => void;
  retrying: boolean;
}

function TargetRow({ target: t, active, onToggle, onRetry, retrying }: RowProps) {
  const st = TARGET_STATUS[t.status];
  const hasCounts = t.status === "done" || t.status === "empty" || t.status === "running";
  return (
    // div, а не button: внутри есть кнопка «Повторить»
    <UnstyledButton
      component="div"
      role="button"
      tabIndex={0}
      className={classes.row}
      data-active={active || undefined}
      onClick={onToggle}
      onKeyDown={(e: React.KeyboardEvent) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggle();
        }
      }}
      title={active ? "Показать все результаты" : "Показать только найденное здесь"}
    >
      <span
        className={`mp-dot ${t.status === "running" ? "mp-pulse" : ""}`}
        style={{ background: DOT[t.status] }}
        aria-hidden="true"
      />
      <PlatformLogo platform={t.platform} size="sm" />
      <span className={classes.name}>
        {t.url && t.kind === "source" ? (
          <Anchor
            href={t.url}
            target="_blank"
            rel="noopener noreferrer"
            size="sm"
            fw={600}
            c="var(--mp-text)"
            onClick={(e) => e.stopPropagation()}
            truncate
          >
            {t.name}
          </Anchor>
        ) : (
          <Text size="sm" fw={600} truncate>
            {t.name}
          </Text>
        )}
        {t.error && (
          <Text size="xs" c="red">
            {t.error.message}
          </Text>
        )}
      </span>
      {hasCounts && (
        <span className={classes.counts}>
          получено {t.fetched} · в подборке {t.matched}
        </span>
      )}
      <span className={classes.status}>{st.label}</span>
      {t.status === "failed" && (
        <Button
          size="compact-xs"
          variant="light"
          loading={retrying}
          onClick={(e) => {
            e.stopPropagation();
            onRetry();
          }}
        >
          Повторить
        </Button>
      )}
    </UnstyledButton>
  );
}
