// История поисков (FE-09): GET /searches, «Показать ещё» по has_more, клик по строке → /search/:id.
import { Alert, Anchor, Badge, Button, Center, Group, Skeleton, Stack, Table, Text, Title } from "@mantine/core";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";

import { api, unwrap, type S } from "../api/client";
import { isFinal, SEARCH_STATUS } from "../features/search/status";
import { fmtDateTime, fmtPeriod } from "../lib/dates";
import { errorText } from "../lib/errors";
import { publications } from "../lib/format";
import { PLATFORM_TITLE } from "../lib/platforms";

const PAGE = 30;
const cut = (s: string, n: number) => {
  const one = s.replace(/\s+/g, " ").trim();
  return one.length > n ? `${one.slice(0, n - 1).trimEnd()}…` : one;
};

export function HistoryPage() {
  const navigate = useNavigate();
  const history = useInfiniteQuery({
    queryKey: ["searches", "history"],
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/api/v1/searches", { params: { query: { limit: PAGE, offset: pageParam } } })),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => (last.has_more ? pages.reduce((n, p) => n + p.items.length, 0) : undefined),
    // пока какой-то поиск в списке идёт — обновляем его статус
    refetchInterval: (q) => (q.state.data?.pages.some((p) => p.items.some((s) => !isFinal(s.status))) ? 5000 : false),
  });
  const items = history.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <Stack>
      <Title order={2}>История</Title>

      {history.isError && !history.data && (
        <Alert color="red" title="Не удалось загрузить историю">
          {errorText(history.error)}{" "}
          <Anchor component="button" type="button" size="sm" onClick={() => history.refetch()}>
            Повторить
          </Anchor>
        </Alert>
      )}

      {history.isSuccess && items.length === 0 && (
        <Stack align="flex-start" gap="sm">
          <Text c="dimmed">Поисков ещё не было.</Text>
          <Button component={Link} to="/">
            Новый поиск
          </Button>
        </Stack>
      )}

      {(history.isPending || items.length > 0) && (
        <Table highlightOnHover verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Запрос</Table.Th>
              <Table.Th w={150}>Период</Table.Th>
              <Table.Th w={200}>Где искали</Table.Th>
              <Table.Th w={150}>Статус</Table.Th>
              <Table.Th w={130}>Найдено</Table.Th>
              <Table.Th w={150}>Когда</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {history.isPending &&
              [0, 1, 2, 3, 4].map((i) => (
                <Table.Tr key={i}>
                  <Table.Td colSpan={6}>
                    <Skeleton height={14} />
                  </Table.Td>
                </Table.Tr>
              ))}
            {items.map((s) => (
              <HistoryRow key={s.id} s={s} onOpen={() => navigate(`/search/${s.id}`)} />
            ))}
          </Table.Tbody>
        </Table>
      )}

      {history.hasNextPage && (
        <Center>
          <Button variant="default" loading={history.isFetchingNextPage} onClick={() => history.fetchNextPage()}>
            Показать ещё
          </Button>
        </Center>
      )}
    </Stack>
  );
}

function HistoryRow({ s, onOpen }: { s: S["SearchSummary"]; onOpen: () => void }) {
  const st = SEARCH_STATUS[s.status];
  const p = s.params;
  return (
    <Table.Tr
      style={{ cursor: "pointer" }}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter") onOpen();
      }}
      tabIndex={0}
      role="link"
      aria-label={`Открыть поиск «${cut(p.query, 60)}»`}
    >
      <Table.Td>
        <Text size="sm" title={p.query.length > 100 ? p.query : undefined}>
          {cut(p.query, 100)}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm">{fmtPeriod(p.period_from, p.period_to)}</Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm">{p.mode === "selected" ? "Мои источники" : "Везде"}</Text>
        <Group gap={4} mt={2}>
          {p.platforms.map((x) => (
            <Badge key={x} variant="outline" color="gray" size="xs">
              {PLATFORM_TITLE[x]}
            </Badge>
          ))}
        </Group>
      </Table.Td>
      <Table.Td>
        <Badge color={st.color} variant="light" style={{ overflow: "visible" }}>
          {st.label}
        </Badge>
      </Table.Td>
      <Table.Td>
        <Text size="sm">{isFinal(s.status) ? publications(s.counts.total) : "—"}</Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm" c="dimmed">
          {fmtDateTime(s.created_at)}
        </Text>
      </Table.Td>
    </Table.Tr>
  );
}
