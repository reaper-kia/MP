import { Loader } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import { Icon } from "../components/Icon";
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
import classes from "./SearchPage.module.css";

export function SearchPage() {
  const { searchId } = useParams();
  const search = useSearch(searchId);
  const [dirty, setDirty] = useState(false);
  const { filters } = useResultFilters();
  useConnectionNotice(search);
  usePageTitle(search.data?.params.query);

  if (!searchId) {
    return (
      <div className={`mp-container ${classes.centered}`}>
        <div className={classes.full}>
          <SearchForm />
        </div>
      </div>
    );
  }

  if (search.isPending) {
    return (
      <div className={`mp-container ${classes.centered}`}>
        <Loader mx="auto" />
      </div>
    );
  }

  if (search.isError && !search.data) {
    const notFound = search.error instanceof ApiError && search.error.code === "SEARCH_NOT_FOUND";
    return (
      <div className={`mp-container ${classes.centered}`}>
        <div className={classes.problem}>
          <span className={classes.problemIcon}>
            <Icon name="search" size={22} />
          </span>
          <h1 className="mp-page-title">{notFound ? "Поиск не найден" : "Не удалось открыть поиск"}</h1>
          <p className="mp-page-lead">{notFound ? "Возможно, ссылка устарела." : errorText(search.error)}</p>
          <Link to="/search" className="mp-accent-button" style={{ marginTop: 24 }}>
            Новый поиск
          </Link>
        </div>
      </div>
    );
  }

  const data = search.data!;
  return (
    <div className={`mp-container ${classes.page}`}>
      {/* key — чтобы при переходе на другой поиск форма заполнилась его параметрами */}
      <SearchForm key={`form-${data.id}`} initial={data.params} onDirtyChange={setDirty} />
      <ParamsBar search={data} dirty={dirty} />
      <SearchProgress search={data} />
      <SearchOutcome search={data} />
      <TargetsPanel search={data} />
      {/* пусто / ошибка без результатов — вкладки с нулями не показываем; «Отсеянные» открываются по ссылке */}
      {(showsResults(data) || filters.tab === "rejected") && <ResultsView key={`results-${data.id}`} search={data} />}
    </div>
  );
}

const BASE_TITLE = document.title;

/** Во вкладке браузера — запрос подборки: несколько открытых поисков различимы (FE-16). */
function usePageTitle(query: string | undefined) {
  useEffect(() => {
    if (!query) return;
    const q = query.replace(/\s+/g, " ").trim();
    document.title = `«${q.length > 60 ? `${q.slice(0, 59).trimEnd()}…` : q}» — МедиаПульс`;
    return () => {
      document.title = BASE_TITLE;
    };
  }, [query]);
}
