import { refreshAccessToken, request, setAccessToken } from "./client";

export * from "./client";

// ── типы ответов Gateway (совпадают со схемами services/gateway/src/gateway/schemas) ──
export type User = {
  id: string;
  email: string | null;
  name: string;
  role: "user" | "admin" | "unknown";
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  access_expires_at: string;
  user: User;
};

export type ItemStatus = "open" | "done";

export type Item = {
  id: string;
  owner_id: string;
  owner_name: string | null;
  title: string;
  description: string;
  status: ItemStatus;
  created_at: string;
  updated_at: string;
};

export type Page<T> = { items: T[]; has_more: boolean };

// ── auth ──
export async function register(email: string, name: string, password: string): Promise<User> {
  const res = await request<AuthResponse>("POST", "/auth/register", { email, name, password });
  setAccessToken(res.access_token);
  return res.user;
}

export async function login(email: string, password: string): Promise<User> {
  const res = await request<AuthResponse>("POST", "/auth/login", { email, password });
  setAccessToken(res.access_token);
  return res.user;
}

export async function logout(): Promise<void> {
  await request<void>("POST", "/auth/logout").catch(() => undefined);
  setAccessToken(null);
}

/** При загрузке страницы: есть refresh-cookie → восстанавливаем сессию. */
export async function restoreSession(): Promise<User | null> {
  if (!(await refreshAccessToken())) return null;
  return request<User>("GET", "/users/me").catch(() => null);
}

// ── items (образец) ──
export const items = {
  list: (offset = 0, limit = 20) => request<Page<Item>>("GET", `/items?limit=${limit}&offset=${offset}`),
  create: (title: string, description = "") => request<Item>("POST", "/items", { title, description }),
  update: (id: string, patch: Partial<Pick<Item, "title" | "description" | "status">>) =>
    request<Item>("PATCH", `/items/${id}`, patch),
  remove: (id: string) => request<void>("DELETE", `/items/${id}`),
};
