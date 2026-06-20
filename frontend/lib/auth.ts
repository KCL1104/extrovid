// Per-user session: the access token (Bearer on every API call) + the cached user record,
// both in localStorage. This module is the single swap-point for the planned move to
// login-only auth (no manual token entry) — keep all token/user storage here.

const KEY = "extrovid_token";
const USER_KEY = "extrovid_user";

export type AuthUser = {
  id: string;
  email: string;
  is_admin: boolean;
  daily_video_cap: number;
  daily_image_cap: number;
  created_at?: string; // ISO; absent on older cached records
  default_format?: string | null; // advisory default for new projects
  has_password?: boolean;
  is_google?: boolean;
};

// Token as an external store: the localStorage value, invalidated by the 401 broadcast or a
// cross-tab `storage` write. Shared by AuthGate and the public gallery (to decide app-shell vs
// bare layout). Server snapshot is null so SSR + first client render agree.
export function subscribeToken(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("extrovid-unauthorized", onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener("extrovid-unauthorized", onChange);
    window.removeEventListener("storage", onChange);
  };
}

export const getToken = (): string | null =>
  typeof window !== "undefined" ? localStorage.getItem(KEY) : null;

export const setToken = (t: string): void => {
  if (typeof window !== "undefined") localStorage.setItem(KEY, t);
};

export const clearToken = (): void => {
  if (typeof window !== "undefined") localStorage.removeItem(KEY);
};

export const getUser = (): AuthUser | null => {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
};

export const setUser = (u: AuthUser): void => {
  if (typeof window !== "undefined") localStorage.setItem(USER_KEY, JSON.stringify(u));
};

export const clearUser = (): void => {
  if (typeof window !== "undefined") localStorage.removeItem(USER_KEY);
};

export const setAuth = (token: string, user: AuthUser): void => {
  setToken(token);
  setUser(user);
};

export const clearAuth = (): void => {
  clearToken();
  clearUser();
};
