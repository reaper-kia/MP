import { Badge, Button, Collapse, Group, Paper, Stack, Text, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";

import type { S } from "../../api/client";
import { PlatformBadge } from "../../components/PlatformBadge";
import { fmtDateTime } from "../../lib/dates";
import { plural } from "../../lib/format";
import { ResultCard } from "./ResultCard";

interface Props {
  group: S["ResultGroup"];
  selected: Set<string>;
  onSelect: (id: string, on: boolean) => void;
  onExclude: (ids: string[], excluded: boolean) => void;
}

export function GroupCard({ group: g, selected, onSelect, onExclude }: Props) {
  const [opened, { toggle }] = useDisclosure(false);

  // Одиночка — сразу карточка, без обёртки сюжета
  if (g.size === 1) {
    const r = g.items[0];
    return (
      <ResultCard
        result={r}
        selected={selected.has(r.id)}
        onSelect={(on) => onSelect(r.id, on)}
        onExclude={(ex) => onExclude([r.id], ex)}
      />
    );
  }

  const date = fmtDateTime(g.earliest_published_at);
  return (
    <Paper withBorder radius="md">
      <UnstyledButton onClick={toggle} p="md" w="100%">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Stack gap={4} style={{ minWidth: 0 }}>
            <Text fw={600}>{g.title}</Text>
            <Group gap="xs">
              <Badge variant="light">
                {g.size} {plural(g.size, ["размещение", "размещения", "размещений"])}
              </Badge>
              {g.platforms.map((p) => (
                <PlatformBadge key={p} platform={p} />
              ))}
              <Text size="sm" c={date ? "dimmed" : "orange"}>
                {date ? `с ${date}` : "Дата недоступна"}
              </Text>
            </Group>
          </Stack>
          <Text size="sm" c="blue" style={{ flexShrink: 0 }}>
            {opened ? "Свернуть" : "Все размещения"}
          </Text>
        </Group>
      </UnstyledButton>
      <Collapse expanded={opened}>
        <Stack gap={4} px="md" pb="md">
          {g.items.map((r) => (
            <ResultCard
              key={r.id}
              compact
              result={r}
              selected={selected.has(r.id)}
              onSelect={(on) => onSelect(r.id, on)}
              onExclude={(ex) => onExclude([r.id], ex)}
            />
          ))}
          <Group>
            <Button
              size="compact-sm"
              variant="subtle"
              color="gray"
              onClick={() => onExclude(g.items.map((r) => r.id), true)}
            >
              Исключить весь сюжет
            </Button>
          </Group>
        </Stack>
      </Collapse>
    </Paper>
  );
}
