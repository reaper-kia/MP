import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type S } from "../../api/client";
import { errorText } from "../../lib/errors";
import { isFinal } from "./status";

/** Поиск по id; пока он не завершён — опрос каждые 1.5 с. */
export function useSearch(searchId: string | undefined) {
  return useQuery({
    queryKey: ["search", searchId],
    queryFn: () => unwrap(api.GET("/api/v1/searches/{search_id}", { params: { path: { search_id: searchId! } } })),
    enabled: !!searchId,
    refetchInterval: (q) => (q.state.data && isFinal(q.state.data.status) ? false : 1500),
  });
}

/** Действие над поиском: ответ (Search) кладём в кэш — опрос возобновится сам, если поиск снова идёт. */
function useSearchAction<V>(searchId: string, run: (vars: V) => Promise<S["Search"]>, failTitle: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: (search) => {
      queryClient.setQueryData(["search", searchId], search);
      queryClient.invalidateQueries({ queryKey: ["results", searchId] });
    },
    onError: (err) => notifications.show({ color: "red", title: failTitle, message: errorText(err) }),
  });
}

/** Повтор упавших целей; без аргумента — все failed. 409 SEARCH_NOT_FINISHED → «Дождитесь окончания поиска». */
export function useRetry(searchId: string) {
  return useSearchAction(
    searchId,
    (targetIds: string[] | undefined) =>
      unwrap(
        api.POST("/api/v1/searches/{search_id}/retry", {
          params: { path: { search_id: searchId } },
          body: { target_ids: targetIds },
        }),
      ),
    "Повтор не запущен",
  );
}

export function useCancel(searchId: string) {
  return useSearchAction(
    searchId,
    () => unwrap(api.POST("/api/v1/searches/{search_id}/cancel", { params: { path: { search_id: searchId } } })),
    "Не удалось остановить поиск",
  );
}
