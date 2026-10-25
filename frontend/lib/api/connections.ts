// connections.ts: the connection desk's data. The guide drafts a connection (waiting), the other side's answer is pasted
// back (delivered), the test passes (tested), an L1 switches it on (live) or off (paused).
// Used by: features/connect/desk*.tsx. Uses: client.ts, hooks.ts (tenant id).
"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { currentPersonaId } from "@/lib/store";
import { apiGet, apiPost, apiSend, tenantPath } from "./client";
import { useTenantId } from "./hooks";

export const TestLine = z.object({ item: z.string(), ok: z.boolean().nullable(), detail: z.string() });
export const Connection = z.object({
  id: z.string(),
  name: z.string(),
  system: z.string(),
  goal: z.string(),
  platform: z.string(),
  kind: z.enum(["api", "database", "other"]),
  later: z.array(z.string()),
  tables: z.array(z.string()),
  status: z.enum(["waiting", "delivered", "tested", "live", "paused"]),
  needs: z.array(z.object({ name: z.string(), label: z.string(), text: z.string(), writes: z.boolean(), required: z.boolean() })),
  baseUrl: z.string().nullable(),
  secretsSet: z.array(z.string()),
  tests: z.array(TestLine),
  testedAt: z.string().nullable(),
  events: z.number(),
  lastEventAt: z.string().nullable(),
  lastError: z.string().nullable(),
});
export type Connection = z.infer<typeof Connection>;
export type TestLine = z.infer<typeof TestLine>;

/** Problems a delivered manifest has, one plain line each, so the other party can fix them. */
export class DeliveryProblems extends Error {
  problems: string[];
  keysKept: string[];
  constructor(problems: string[], keysKept: string[] = []) {
    super(problems[0] ?? "Not accepted");
    this.problems = problems;
    this.keysKept = keysKept;
  }
}

export function useConnections() {
  const tenantId = useTenantId();
  return useQuery({ queryKey: ["t", tenantId, "connections"], queryFn: ({ signal }) => apiGet("connections", z.array(Connection), signal), refetchInterval: 5000 });
}

export function useBrief(id: string) {
  const tenantId = useTenantId();
  return useQuery({ queryKey: ["t", tenantId, "connections", id, "brief"], queryFn: ({ signal }) => apiGet(`connections/${id}/brief`, z.object({ brief: z.string() }), signal) });
}

/** One mutation per desk action; each refreshes the list so the card shows the new status. */
export function useConnectionAction<A, R = Connection>(run: (args: A) => Promise<R>) {
  const queryClient = useQueryClient();
  const tenantId = useTenantId();
  return useMutation({ mutationFn: run, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["t", tenantId, "connections"] }) });
}

export const createConnection = (name: string) => apiPost("connections", { name }, Connection);
export const testConnection = (id: string) => apiPost(`connections/${id}/test`, {}, Connection);
export const switchConnection = (id: string, on: boolean) => apiPost(`connections/${id}/live`, { on }, Connection);
export const renameConnection = ({ id, name }: { id: string; name: string }) => apiSend("PATCH", `connections/${id}`, { name }, Connection);
export const deleteConnection = (id: string) => apiSend("DELETE", `connections/${id}`, {}, z.object({ deleted: z.string() }));
export type Turn = { role: "user" | "assistant"; text: string };
/** The guide answers; when it drafts, the connection comes back created or updated. */
export type Kind = Connection["kind"];
/** The guide answers; when it drafts, the connection comes back created or updated. A new one starts with its type and platform. */
export const askGuide = (id: string | null, turns: Turn[], start?: { kind: Kind; platform: string; fromConnection?: string; fromItem?: string }) =>
  apiPost(id ? `connections/${id}/guide` : "connections/guide", { turns, ...start }, z.object({ answer: z.string(), connection: Connection.nullable() }));

/** Connections grouped by the platform they belong to, platforms in name order. */
export function byPlatform(list: Connection[]): [string, Connection[]][] {
  const groups = new Map<string, Connection[]>();
  for (const c of list) groups.set(c.platform, [...(groups.get(c.platform) ?? []), c]);
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

/** Deliver reads the 422 itself, because its problems are a list, not one message. */
export async function deliverConnection(id: string, body: { answer: string }): Promise<Connection> {
  const res = await fetch(tenantPath(`connections/${id}/deliver`), {
    method: "POST",
    headers: { "content-type": "application/json", "x-persona": currentPersonaId() },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 422) throw new DeliveryProblems(data?.error?.problems ?? ["Not accepted"], data?.error?.keysKept ?? []);
  if (!res.ok) throw new Error(typeof data?.error === "string" ? data.error : `${res.status}`);
  return Connection.parse(data);
}
