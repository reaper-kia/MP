import { Button, Center, Loader, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, ApiError, unwrap } from "../api/client";
import { SearchForm } from "../features/search/SearchForm";
import { errorText } from "../lib/errors";

export function SearchPage() {
  const { searchId } = useParams();

  const search = useQuery({
    queryKey: ["search", searchId],
    queryFn: () => unwrap(api.GET("/api/v1/searches/{search_id}", { params: { path: { search_id: searchId! } } })),
    enabled: !!searchId,
  });

  if (!searchId) {
    return (
      <Stack>
        <Title order={2}>Поиск публикаций</Title>
        <SearchForm />
      </Stack>
    );
  }

  if (search.isPending) {
    return (
      <Center mt="xl">
        <Loader />
      </Center>
    );
  }

  if (search.isError) {
    const notFound = search.error instanceof ApiError && search.error.status === 404;
    return (
      <Stack align="flex-start">
        <Title order={2}>{notFound ? "Поиск не найден" : "Не удалось открыть поиск"}</Title>
        <Text c="dimmed">{notFound ? "Возможно, ссылка устарела." : errorText(search.error)}</Text>
        <Button component={Link} to="/">
          Новый поиск
        </Button>
      </Stack>
    );
  }

  return (
    <Stack>
      {/* key — чтобы при переходе на другой поиск форма заполнилась его параметрами */}
      <SearchForm key={search.data.id} initial={search.data.params} />
      {/* Ход поиска и подборка — FE-04…FE-07 */}
      <Text c="dimmed">Статус поиска: {search.data.status}. Подборка появится в FE-04…FE-07.</Text>
    </Stack>
  );
}
