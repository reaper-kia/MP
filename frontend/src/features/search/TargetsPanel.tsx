import { Accordion, Anchor, Badge, Button, Group, Stack, Text, UnstyledButton } from "@mantine/core";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";

import type { S } from "../../api/client";
import { PLATFORM_TITLE } from "../../lib/platforms";
import { isFinal, TARGET_STATUS } from "./status";
import { useRetry } from "./useSearch";
import classes from "./TargetsPanel.module.css";

const ITEM = "targets";

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
    <Accordion variant="contained" radius="md" value={open} onChange={setOpen}>
      <Accordion.Item value={ITEM}>
        <Accordion.Control>
          <Group gap="xs" wrap="wrap">
            <Text fw={500}>Где искали</Text>
            <Text size="sm" c="dimmed">
              Обработано {processed} из {search.targets.length}
              {failed > 0 && (
                <>
                  {" · "}
                  <Text span c="red" size="sm">
                    не удалось: {failed}
                  </Text>
                </>
              )}
              {activeTargets.length > 0 && " · подборка отфильтрована по источнику"}
            </Text>
          </Group>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap={4}>
            {final && failed > 0 && (
              <Group>
                <Button size="compact-sm" variant="light" loading={retry.isPending} onClick={() => retry.mutate(undefined)}>
                  Повторить все неудачные
                </Button>
              </Group>
            )}
            {search.targets.length === 0 && (
              <Text size="sm" c="dimmed">
                Список источников появится, когда поиск начнётся.
              </Text>
            )}
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
          </Stack>
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
      className={active ? `${classes.row} ${classes.active}` : classes.row}
      onClick={onToggle}
      onKeyDown={(e: React.KeyboardEvent) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onToggle();
        }
      }}
      title={active ? "Показать все результаты" : "Показать только найденное здесь"}
    >
      <Group justify="space-between" wrap="nowrap" gap="sm">
        <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
          <Badge variant="outline" color="gray" w={78} style={{ flexShrink: 0 }}>
            {PLATFORM_TITLE[t.platform]}
          </Badge>
          <Stack gap={0} style={{ minWidth: 0 }}>
            {t.url && t.kind === "source" ? (
              <Anchor href={t.url} target="_blank" rel="noopener noreferrer" size="sm" onClick={(e) => e.stopPropagation()} truncate>
                {t.name}
              </Anchor>
            ) : (
              <Text size="sm" truncate>
                {t.name}
              </Text>
            )}
            {t.error && (
              <Text size="xs" c="red">
                {t.error.message}
              </Text>
            )}
          </Stack>
        </Group>
        <Group gap="sm" wrap="nowrap" style={{ flexShrink: 0 }}>
          {hasCounts && (
            <Text size="xs" c="dimmed">
              получено {t.fetched} · в подборке {t.matched}
            </Text>
          )}
          <Badge color={st.color} variant="light">
            {st.label}
          </Badge>
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
        </Group>
      </Group>
    </UnstyledButton>
  );
}
