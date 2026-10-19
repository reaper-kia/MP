// Клиент к Gateway на openapi-fetch. Типы — из contracts/http/openapi.yaml (npm run gen:api).
// Авторизации нет. Любой не-2xx ответ превращается в ApiError с кодом из тела ошибки.
import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type S = components["schemas"]; // S["Search"], S["Result"], ...

export type ErrorDetail = { field?: string; message?: string; [key: string]: unknown };

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: ErrorDetail[] = [],
    public requestId = "",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const throwOnError: Middleware = {
  async onResponse({ response }) {
    if (response.ok) return;
    const body = (await response.clone().json().catch(() => null)) as S["ErrorResponse"] | null;
    const err = body?.error;
    throw new ApiError(
      response.status,
      err?.code ?? "UNKNOWN",
      err?.message ?? response.statusText,
      (err?.details as ErrorDetail[] | undefined) ?? [],
      err?.request_id ?? response.headers.get("X-Request-ID") ?? "",
    );
  },
};

export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL ?? "",
  querySerializer: { array: { style: "form", explode: true } },
});
api.use(throwOnError);

/** Ошибки уже брошены middleware, поэтому data на этом месте всегда есть (кроме 204). */
export async function unwrap<T>(req: Promise<{ data?: T }>): Promise<T> {
  const { data } = await req;
  return data as T;
}
