import { Button, Group, Paper, Progress, Stack, Text } from "@mantine/core";

import type { S } from "../../api/client";
import { isFinal, stageText } from "./status";
import { useCancel } from "./useSearch";

/** Стадия и прогресс, пока поиск идёт; предупреждения — всегда. */
export function SearchProgress({ search }: { search: S["Search"] }) {
  const cancel = useCancel(search.id);
  const running = !isFinal(search.status);
  if (!running && search.warnings.length === 0) return null;

  return (
    <Paper withBorder p="md" radius="md">
      <Stack gap="xs">
        {running && (
          <>
            <Group justify="space-between">
              <Text fw={500}>{stageText(search)}</Text>
              <Button
                variant="default"
                size="compact-sm"
                loading={cancel.isPending}
                onClick={() => cancel.mutate(undefined)}
              >
                Остановить
              </Button>
            </Group>
            <Progress value={search.progress.percent} animated striped />
          </>
        )}
        {search.warnings.map((w) => (
          <Text key={w} size="sm" c="dimmed">
            {w}
          </Text>
        ))}
      </Stack>
    </Paper>
  );
}
