// Тонкий клиент к Gateway. Access-токен — только в памяти, refresh — в HttpOnly cookie.
// На 401 клиент один раз пробует /auth/refresh и повторяет запрос.

export type ErrorDetail = { field: string; reason: string };

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: ErrorDetail[] = [],
    public requestId?: string,
  ) {
    super(message);
  }
}

let accessToken: string | null = null;
const listeners = new Set<(token: string | null) => void>();

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
  listeners.forEach((fn) => fn(token));
}

export function onAccessTokenChange(fn: (token: string | null) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

let refreshing: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  // несколько параллельных 401 → один refresh
  refreshing ??= fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" })
    .then(async (res) => {
      if (!res.ok) {
        setAccessToken(null);
        return false;
      }
      const data = (await res.json()) as { access_token: string };
      setAccessToken(data.access_token);
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
const NO_RETRY = new Set(["/auth/login", "/auth/register", "/auth/refresh"]);

export async function request<T>(method: Method, path: string, body?: unknown, retry = true): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const res = await fetch(`/api/v1${path}`, {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (res.status === 401 && retry && !NO_RETRY.has(path) && (await refreshAccessToken())) {
    return request<T>(method, path, body, false);
  }
  if (res.status === 204) return undefined as T;

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error;
    throw new ApiError(
      res.status,
      err?.code ?? "UNKNOWN",
      err?.message ?? res.statusText,
      err?.details ?? [],
      err?.request_id ?? res.headers.get("X-Request-ID") ?? undefined,
    );
  }
  return data as T;
}

export { refreshAccessToken };
