import { Button, Center, Loader, Stack, Text, Title } from "@mantine/core";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import { useResultFilters } from "../features/results/filters";
import { ResultsView } from "../features/results/ResultsView";
import { ParamsBar } from "../features/search/ParamsBar";
import { SearchForm } from "../features/search/SearchForm";
import { SearchOutcome } from "../features/search/SearchOutcome";
import { SearchProgress } from "../features/search/SearchProgress";
import { TargetsPanel } from "../features/search/TargetsPanel";
import { useSearch } from "../features/search/useSearch";
import { showsResults } from "../features/search/viewState";
import { errorText } from "../lib/errors";
import { useConnectionNotice } from "../lib/useConnectionNotice";

export function SearchPage() {
  const { searchId } = useParams();
  const search = useSearch(searchId);
  const [dirty, setDirty] = useState(false);
  const { filters } = useResultFilters();
  useConnectionNotice(search);

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
      <SearchForm key={`form-${data.id}`} initial={data.params} onDirtyChange={setDirty} />
      <ParamsBar search={data} dirty={dirty} />
      <SearchProgress search={data} />
      <SearchOutcome search={data} />
      <TargetsPanel search={data} />
      {/* пусто / ошибка без результатов — вкладки с нулями не показываем; «Отсеянные» открываются по ссылке */}
      {(showsResults(data) || filters.tab === "rejected") && <ResultsView key={`results-${data.id}`} search={data} />}
    </Stack>
  );
}
