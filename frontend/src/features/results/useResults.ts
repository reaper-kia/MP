import { notifications } from "@mantine/notifications";
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";

import { api, ApiError, unwrap, type S } from "../../api/client";
import { errorText } from "../../lib/errors";
import { groupsQuery, listQuery, type ResultFilters } from "./filters";

const PAGE = 50;
// Пока поиск идёт, результаты прибывают — перезапрашиваем раз в 3 с
const POLL_MS = 3000;

type Page = { items: unknown[]; has_more: boolean };
const nextOffset = (last: Page, pages: Page[]) =>
  last.has_more ? pages.reduce((n, p) => n + p.items.length, 0) : undefined;

export function useResultList(searchId: string, f: ResultFilters, running: boolean, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: ["results", searchId, "list", f],
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/searches/{search_id}/results", {
          params: { path: { search_id: searchId }, query: { ...listQuery(f), limit: PAGE, offset: pageParam } },
        }),
      ),
    initialPageParam: 0,
    getNextPageParam: nextOffset,
    refetchInterval: running ? POLL_MS : false,
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useGroupList(searchId: string, f: ResultFilters, running: boolean, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: ["results", searchId, "groups", f],
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/searches/{search_id}/groups", {
          params: { path: { search_id: searchId }, query: { ...groupsQuery(f), limit: PAGE, offset: pageParam } },
        }),
      ),
    initialPageParam: 0,
    getNextPageParam: nextOffset,
    refetchInterval: running ? POLL_MS : false,
    placeholderData: keepPreviousData,
    enabled,
  });
}

type ListData = InfiniteData<S["ResultPage"]>;
type GroupData = InfiniteData<S["GroupPage"]>;

/**
 * Исключить / вернуть. Оптимистично: из списков без «показать исключённые» карточки сразу пропадают,
 * в списках с ними — помечаются. После ответа — новые counts в кэш поиска и перезапрос списков.
 */
export function useExclusion(searchId: string) {
  const queryClient = useQueryClient();
  const key = ["results", searchId];

  return useMutation({
    mutationFn: (vars: { ids: string[]; excluded: boolean }) =>
      unwrap(
        api.POST("/api/v1/searches/{search_id}/results/exclusion", {
          params: { path: { search_id: searchId } },
          body: { result_ids: vars.ids, excluded: vars.excluded },
        }),
      ),
    onMutate: async ({ ids, excluded }) => {
      await queryClient.cancelQueries({ queryKey: key });
      const snapshot = queryClient.getQueriesData({ queryKey: key });
      const hit = new Set(ids);
      const patch = (r: S["Result"]) => (hit.has(r.id) ? { ...r, excluded } : r);

      for (const [qk, data] of snapshot) {
        if (!data) continue;
        const kind = qk[2];
        const showExcluded = (qk[3] as ResultFilters | undefined)?.include_excluded ?? false;
        const keep = (r: S["Result"]) => showExcluded || !(excluded && hit.has(r.id));
        if (kind === "list") {
          const d = data as ListData;
          queryClient.setQueryData<ListData>(qk, {
            ...d,
            pages: d.pages.map((p) => ({ ...p, items: p.items.map(patch).filter(keep) })),
          });
        } else if (kind === "groups") {
          const d = data as GroupData;
          queryClient.setQueryData<GroupData>(qk, {
            ...d,
            pages: d.pages.map((p) => ({
              ...p,
              items: p.items
                .map((g) => {
                  const items = g.items.map(patch).filter(keep);
                  return { ...g, items, size: items.length };
                })
                .filter((g) => g.items.length > 0),
            })),
          });
        }
      }
      return { snapshot };
    },
    onSuccess: ({ counts }) => {
      queryClient.setQueryData<S["Search"]>(["search", searchId], (s) => (s ? { ...s, counts } : s));
      // «в подборке N» у источников в «Где искали» сервер тоже пересчитал — перечитать поиск
      queryClient.invalidateQueries({ queryKey: ["search", searchId] });
    },
    onError: (err, _vars, ctx) => {
      ctx?.snapshot.forEach(([qk, data]) => queryClient.setQueryData(qk, data));
      // RESULT_NOT_FOUND — список устарел, просто обновим его молча
      if (!(err instanceof ApiError && err.code === "RESULT_NOT_FOUND")) {
        notifications.show({ color: "red", title: "Не удалось изменить подборку", message: errorText(err) });
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}
