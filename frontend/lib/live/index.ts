"use client";

import { config, flags } from "@/lib/flags";

export type LiveEvent = { type: string; tenantId: string; at: string; resources: string[]; summary: string };
export type LiveSource = { subscribe: (tenantId: string, onEvent: (e: LiveEvent) => void) => () => void };

/** Mock source: the in-browser mock database and its timer driven stream. */
const mockSource: LiveSource = {
  subscribe(tenantId, onEvent) {
    let unsub: (() => void) | null = null;
    let cancelled = false;
    import("@/lib/mock/db").then(({ db }) => {
      if (cancelled) return;
      if (flags.mockStream) db.startStream();
      unsub = (() => {
        const off = db.subscribe((e) => {
          if (e.tenantId === tenantId || e.tenantId === "*") onEvent(e);
        });
        return () => void off();
      })();
    });
    return () => {
      cancelled = true;
      unsub?.();
    };
  },
};

/** SSE source for the real backend: GET /api/t/{tenant}/stream emits LiveEvent JSON per message. */
const sseSource: LiveSource = {
  subscribe(tenantId, onEvent) {
    const es = new EventSource(`${config.apiBaseUrl}/api/t/${tenantId}/stream`);
    es.onmessage = (m) => {
      try {
        onEvent(JSON.parse(m.data) as LiveEvent);
      } catch {
        // Ignore malformed frames.
      }
    };
    return () => es.close();
  },
};

export const live: LiveSource = config.liveSource === "sse" && !flags.mocks ? sseSource : mockSource;
