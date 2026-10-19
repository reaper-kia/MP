import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../../api/client";

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
