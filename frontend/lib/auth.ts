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
};

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
