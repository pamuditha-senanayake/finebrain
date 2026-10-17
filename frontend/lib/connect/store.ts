"use client";

import { useEffect, useState } from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Method } from "./catalog";

/**
 * Connections and the setup answers live in the browser for now. There is no backend for them yet,
 * so a new connection walks through Connecting, Reading and In knowledge on a timer to show the flow.
 */
export type Connection = {
  id: string;
  connectorId: string;
  name: string;
  method: Method | "request";
  /** What the brain listens to: inboxes, channels, repos, a host, a URL or file names. */
  detail: string;
  addedAt: number;
  /** Off pauses listening without losing the connection. Missing means on. */
  enabled?: boolean;
};

export type Profile = { name: string; website: string; about: string; tools: string[]; other: string; mcps: string[] };

export const CLAUDE_TOOLS = [
  { id: "ask", label: "Ask the brain", on: true },
  { id: "search", label: "Search knowledge", on: true },
  { id: "policies", label: "Read policies", on: true },
  { id: "workflows", label: "See workflows", on: true },
  { id: "propose", label: "Propose changes", on: false, hint: "Goes to approvals" },
] as const;

type ConnectState = {
  connections: Connection[];
  profile: Profile;
  step: number;
  claudeTools: Record<string, boolean>;
  /** Sensors from the backend switched off here. Only in the browser until the backend can pause them. */
  sensorsOff: Record<string, boolean>;
  connect: (c: Omit<Connection, "id" | "addedAt">) => void;
  disconnect: (id: string) => void;
  setEnabled: (id: string, on: boolean) => void;
  setSensorOn: (id: string, on: boolean) => void;
  setProfile: (p: Partial<Profile>) => void;
  setStep: (step: number) => void;
  resetSetup: () => void;
  setClaudeTool: (id: string, on: boolean) => void;
};

const EMPTY: Profile = { name: "", website: "", about: "", tools: [], other: "", mcps: [] };

export const useConnect = create<ConnectState>()(
  persist(
    (set) => ({
      connections: [],
      profile: EMPTY,
      step: 0,
      claudeTools: Object.fromEntries(CLAUDE_TOOLS.map((t) => [t.id, t.on])),
      sensorsOff: {},
      connect: (c) =>
        set((s) => ({
          // Connecting the same thing twice replaces the older one.
          connections: [...s.connections.filter((x) => !(x.connectorId === c.connectorId && x.detail === c.detail)), { ...c, id: `${c.connectorId}-${Date.now()}`, addedAt: Date.now() }],
        })),
      disconnect: (id) => set((s) => ({ connections: s.connections.filter((x) => x.id !== id) })),
      setEnabled: (id, on) => set((s) => ({ connections: s.connections.map((x) => (x.id === id ? { ...x, enabled: on } : x)) })),
      setSensorOn: (id, on) => set((s) => ({ sensorsOff: { ...s.sensorsOff, [id]: !on } })),
      setProfile: (p) => set((s) => ({ profile: { ...s.profile, ...p } })),
      setStep: (step) => set({ step }),
      resetSetup: () => set({ profile: EMPTY, step: 0 }),
      setClaudeTool: (id, on) => set((s) => ({ claudeTools: { ...s.claudeTools, [id]: on } })),
    }),
    { name: "cb.connect.v1", storage: createJSONStorage(() => localStorage) },
  ),
);

export type Stage = "connecting" | "reading" | "known" | "requested" | "paused";

/** Where a connection is on its way into knowledge, from how long ago it was added. */
export function stageOf(c: Connection, now: number): Stage {
  if (c.method === "request") return "requested";
  if (c.enabled === false) return "paused";
  const age = now - c.addedAt;
  return age < 4000 ? "connecting" : age < 16000 ? "reading" : "known";
}

export const STAGE_LABEL: Record<Stage, string> = { connecting: "Connecting", reading: "Reading", known: "In knowledge", requested: "Requested", paused: "Off" };

/** When the last sync ran: first when reading ends, then every 15 minutes. Demo timing until the backend reports it. */
export function lastSyncOf(c: Connection, now: number) {
  const first = c.addedAt + 16000;
  if (now < first) return null;
  return first + Math.floor((now - first) / 900_000) * 900_000;
}

/** A steady demo count of items learned, so the same connection always shows the same number. */
export function itemsOf(c: Connection) {
  let h = 0;
  for (const ch of c.id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return 120 + (h % 2300);
}

/** The current time, ticking each second until the newest connection has reached knowledge, so stages move on screen. */
export function useStageClock(connections: Connection[]) {
  const [now, setNow] = useState(() => Date.now());
  const newest = connections.reduce((m, c) => Math.max(m, c.addedAt), 0);
  useEffect(() => {
    const t = setInterval(() => {
      const n = Date.now();
      setNow(n);
      if (n - newest > 17000) clearInterval(t);
    }, 1000);
    return () => clearInterval(t);
  }, [newest]);
  return now;
}
