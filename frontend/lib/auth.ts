// Shared access token, stored in localStorage. Sent as Bearer on every API call.

const KEY = "extrovid_token";

export const getToken = (): string | null =>
  typeof window !== "undefined" ? localStorage.getItem(KEY) : null;

export const setToken = (t: string): void => {
  if (typeof window !== "undefined") localStorage.setItem(KEY, t);
};

export const clearToken = (): void => {
  if (typeof window !== "undefined") localStorage.removeItem(KEY);
};
