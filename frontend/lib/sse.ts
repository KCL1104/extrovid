// Server-Sent Events over fetch() — NOT EventSource, which can't send the Authorization
// header our Bearer-token API requires. Reads the ReadableStream, parses `data:` frames,
// and replicates api()'s 401 -> clearAuth behavior (the raw reader bypasses that path).

import { API_BASE } from "@/lib/api";
import { clearAuth, getToken } from "@/lib/auth";

export type SSEvent = { type: string; [k: string]: unknown };

export async function streamSSE(
  path: string,
  opts: {
    method?: string;
    body?: unknown;
    signal?: AbortSignal;
    onEvent: (event: SSEvent) => void;
  },
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method ?? "GET",
    headers: {
      Accept: "text/event-stream",
      ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
    cache: "no-store",
  });

  if (res.status === 401) {
    clearAuth();
    if (typeof window !== "undefined") window.dispatchEvent(new Event("extrovid-unauthorized"));
    throw new Error("Unauthorized — please sign in again.");
  }
  if (!res.ok || !res.body) throw new Error(`stream failed (${res.status})`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? ""; // keep the trailing incomplete frame
    for (const frame of frames) {
      const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!dataLine) continue; // keepalive comment frames (":") carry no data
      const payload = dataLine.slice(5).trim();
      if (!payload) continue;
      try {
        opts.onEvent(JSON.parse(payload) as SSEvent);
      } catch {
        /* ignore a malformed frame */
      }
    }
  }
}
