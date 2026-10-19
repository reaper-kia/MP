import { Alert, Button, Group, Paper, Text } from "@mantine/core";

import type { S } from "../../api/client";
import { dayjs } from "../../lib/dates";
import { publications } from "../../lib/format";
import { PLATFORM_TITLE } from "../../lib/platforms";
import classes from "./ParamsBar.module.css";

const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);

/** К каким условиям относится показанная подборка. Липнет под шапкой при прокрутке. */
export function ParamsBar({ search, dirty }: { search: S["Search"]; dirty: boolean }) {
  const p = search.params;
  const from = dayjs(p.period_from);
  const to = dayjs(p.period_to);
  const period =
    p.period_from === p.period_to ? to.format("DD.MM.YYYY") : `${from.format("DD.MM")}–${to.format("DD.MM.YYYY")}`;

  return (
    <div className={classes.sticky}>
      <Paper withBorder p="xs" px="md" radius="md" shadow="xs">
        <Text size="sm">
          Подборка: «{cut(p.query.replace(/\s+/g, " "), 80)}» · {period} ·{" "}
          {p.mode === "selected" ? "Только мои источники" : "Везде"} · {p.platforms.map((x) => PLATFORM_TITLE[x]).join(", ")} ·{" "}
          <b>{publications(search.counts.total)}</b>
        </Text>
      </Paper>
      {dirty && (
        <Alert color="yellow" variant="light" p="xs" mt={6}>
          <Group justify="space-between" wrap="nowrap">
            <Text size="sm">Параметры изменены. Ниже — подборка по прежним условиям.</Text>
            {/* сабмит формы поиска по id — та же валидация, что у кнопки «Найти» */}
            <Button size="compact-sm" type="submit" form="search-form">
              Найти заново
            </Button>
          </Group>
        </Alert>
      )}
    </div>
  );
}
