import { Alert, Anchor, Badge, Loader, Stack, Table, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../api/client";
import { PLATFORM_TITLE } from "../lib/platforms";

// Пока только просмотр списка (DoD FE-01). Фильтры, добавление, правка — FE-08.
export function SourcesPage() {
  const sources = useQuery({
    queryKey: ["sources", { limit: 50, offset: 0 }],
    queryFn: () => unwrap(api.GET("/api/v1/sources", { params: { query: { limit: 50, offset: 0 } } })),
  });

  return (
    <Stack>
      <Title order={2}>Источники</Title>
      {sources.isPending && <Loader />}
      {sources.isError && (
        <Alert color="red" title="Не удалось загрузить источники">
          {sources.error.message}
        </Alert>
      )}
      {sources.data && (
        <>
          <Text c="dimmed" size="sm">
            Всего: {sources.data.total}
          </Text>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Площадка</Table.Th>
                <Table.Th>Название</Table.Th>
                <Table.Th>Город</Table.Th>
                <Table.Th>Региональный</Table.Th>
                <Table.Th>Активный</Table.Th>
                <Table.Th>Заметка</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sources.data.items.map((s) => (
                <Table.Tr key={s.id}>
                  <Table.Td>{PLATFORM_TITLE[s.platform]}</Table.Td>
                  <Table.Td>
                    <Anchor href={s.url} target="_blank" rel="noopener noreferrer">
                      {s.name}
                    </Anchor>
                  </Table.Td>
                  <Table.Td>{s.city ?? "—"}</Table.Td>
                  <Table.Td>{s.is_regional ? <Badge variant="light">да</Badge> : "нет"}</Table.Td>
                  <Table.Td>{s.is_active ? "да" : "нет"}</Table.Td>
                  <Table.Td>{s.notes}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </>
      )}
    </Stack>
  );
}
