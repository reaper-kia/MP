import { Button, Center, Loader, Stack, Text, Title } from "@mantine/core";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import { SearchForm } from "../features/search/SearchForm";
import { SearchProgress } from "../features/search/SearchProgress";
import { TargetsPanel } from "../features/search/TargetsPanel";
import { useSearch } from "../features/search/useSearch";
import { errorText } from "../lib/errors";

export function SearchPage() {
  const { searchId } = useParams();
  const search = useSearch(searchId);

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

  if (search.isError && !search.data) {
    const notFound = search.error instanceof ApiError && search.error.code === "SEARCH_NOT_FOUND";
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

  const data = search.data!;
  return (
    <Stack>
      {/* key — чтобы при переходе на другой поиск форма заполнилась его параметрами */}
      <SearchForm key={data.id} initial={data.params} />
      <SearchProgress search={data} />
      <TargetsPanel search={data} />
      {/* Подборка — FE-05…FE-07 */}
    </Stack>
  );
}
