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

// Анонимный id браузера (не вход): сервер показывает в «Истории» только поиски с этим id.
// Хранится в localStorage; где его нет (service worker расширения, запрет хранилища) — в памяти.
// crypto.randomUUID работает только по https, а стенд открыт по http — поэтому getRandomValues.
const CLIENT_ID_KEY = "mp_client_id";
const CLIENT_ID_RE = /^[A-Za-z0-9-]{8,64}$/;
let cachedClientId = "";

function randomId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function clientId(): string {
  if (cachedClientId) return cachedClientId;
  let id = "";
  try {
    id = globalThis.localStorage?.getItem(CLIENT_ID_KEY) ?? "";
  } catch {
    id = ""; // хранилище запрещено — id только на эту вкладку
  }
  if (!CLIENT_ID_RE.test(id)) {
    id = randomId();
    try {
      globalThis.localStorage?.setItem(CLIENT_ID_KEY, id);
    } catch {
      // не сохранилось — история живёт до перезагрузки страницы
    }
  }
  cachedClientId = id;
  return id;
}

const withClientId: Middleware = {
  async onRequest({ request }) {
    request.headers.set("X-Client-Id", clientId());
    return request;
  },
};

// Адрес сервера, заданный во время работы (расширение FE-17: меняется в настройках). Пусто — baseUrl сборки.
let serverOverride = "";

/** Расширение: все запросы api — на этот адрес (например, http://109.196.167.204:8080). */
export function setApiServer(url: string) {
  serverOverride = url.trim().replace(/\/+$/, "");
}

export const apiUrl = (path: string) => `${serverOverride || (import.meta.env.VITE_API_URL ?? "")}${path}`;

const serverRewrite: Middleware = {
  async onRequest({ request }) {
    if (!serverOverride) return undefined;
    const u = new URL(request.url);
    const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();
    return new Request(serverOverride + u.pathname + u.search, {
      method: request.method,
      headers: request.headers,
      body,
      signal: request.signal,
    });
  },
};

export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL ?? "",
  querySerializer: { array: { style: "form", explode: true } },
});
api.use(withClientId, serverRewrite, throwOnError);

/** Ошибки уже брошены middleware, поэтому data на этом месте всегда есть (кроме 204). */
export async function unwrap<T>(req: Promise<{ data?: T }>): Promise<T> {
  const { data } = await req;
  return data as T;
}
