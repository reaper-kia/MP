// Каталог источников (FE-08): список с фильтрами, предпросмотр по ссылке, добавление, правка, удаление.
// Все ключи — под ["sources"], чтобы правка здесь обновляла и выбор источников в форме поиска.
import { notifications } from "@mantine/notifications";
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";

import { api, unwrap, type S } from "../../api/client";
import { errorText } from "../../lib/errors";

export const SOURCES_PAGE = 50;

export interface SourceFilters {
  q: string;
  platform: S["Platform"] | null;
  page: number; // с 1
}

export function useSourcePage(f: SourceFilters) {
  return useQuery({
    queryKey: ["sources", "page", f],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/sources", {
          params: {
            query: {
              q: f.q || undefined,
              platform: f.platform ? [f.platform] : undefined,
              limit: SOURCES_PAGE,
              offset: (f.page - 1) * SOURCES_PAGE,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

/** Источники одной площадки для раскрывающегося блока на странице «Источники»: по 50, «Показать ещё». */
export function usePlatformSources(platform: S["Platform"], q: string, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: ["sources", "platform", platform, q],
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/sources", {
          params: { query: { platform: [platform], q: q || undefined, limit: SOURCES_PAGE, offset: pageParam } },
        }),
      ),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => (last.has_more ? pages.reduce((n, p) => n + p.items.length, 0) : undefined),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useResolveSource() {
  return useMutation({
    mutationFn: (url: string) => unwrap(api.POST("/api/v1/sources/resolve", { body: { url } })),
  });
}

export function useCreateSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: S["SourceCreateIn"]) => unwrap(api.POST("/api/v1/sources", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });
}

type SourcePage = S["SourcePage"];
type SourceCache = SourcePage | InfiniteData<SourcePage> | undefined;

const patchPage = (page: SourcePage, id: string, patch: S["SourceUpdateIn"]): SourcePage => ({
  ...page,
  items: page.items.map((s) => (s.id === id ? ({ ...s, ...patch } as S["Source"]) : s)),
});

/** PATCH со сдвигом в кэше сразу (переключатели), откат и уведомление при ошибке. */
export function useUpdateSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: S["SourceUpdateIn"] }) =>
      unwrap(api.PATCH("/api/v1/sources/{source_id}", { params: { path: { source_id: id } }, body: patch })),
    // все списки каталога (страницы, весь каталог, блоки площадок) — сразу, до ответа сервера
    onMutate: async ({ id, patch }) => {
      await queryClient.cancelQueries({ queryKey: ["sources"] });
      const snapshot = queryClient.getQueriesData<SourceCache>({ queryKey: ["sources"] });
      for (const [key, data] of snapshot) {
        if (!data) continue;
        if ("pages" in data) {
          queryClient.setQueryData<InfiniteData<SourcePage>>(key, {
            ...data,
            pages: data.pages.map((p) => patchPage(p, id, patch)),
          });
        } else if ("items" in data) {
          queryClient.setQueryData<SourcePage>(key, patchPage(data, id, patch));
        }
      }
      return { snapshot };
    },
    onError: (err, _vars, ctx) => {
      ctx?.snapshot.forEach(([key, data]) => queryClient.setQueryData(key, data));
      notifications.show({ color: "red", title: "Изменение не сохранено", message: errorText(err, "source") });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });
}

export function useDeleteSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.DELETE("/api/v1/sources/{source_id}", { params: { path: { source_id: id } } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });
}
