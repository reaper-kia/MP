import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, unwrap, type S } from "../../api/client";

export function usePlatforms() {
  return useQuery({
    queryKey: ["platforms"],
    queryFn: () => unwrap(api.GET("/api/v1/platforms")),
    staleTime: 5 * 60_000,
  });
}

/** Весь каталог (до 200) — для чипов выбранных и выбора «по умолчанию». */
export function useAllSources() {
  return useQuery({
    queryKey: ["sources", "all"],
    queryFn: () => unwrap(api.GET("/api/v1/sources", { params: { query: { limit: 200, offset: 0 } } })),
    staleTime: 60_000,
  });
}

/** Площадки без поиска по всей площадке — для пометок режима «Везде» (FE-14). */
export function useNoGlobal(): ReadonlySet<S["Platform"]> {
  const { data } = usePlatforms();
  return useMemo(() => new Set((data ?? []).filter((p) => !p.global_mode).map((p) => p.code)), [data]);
}
