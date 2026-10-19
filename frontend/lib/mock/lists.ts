// lists.ts: the mock twin of backend/app/api/lists_query.py (step 12). The same page contract over mock data, so demo
// tenants page, filter, search and jump to a row the way Finebase HQ does. Used by handlers.ts.
import type { Run } from "@/contracts";
import type { TenantData } from "./types";

const PAGE = 100;
const MOST = 500;
const MOST_MATCHES = 5000;

type Row = Record<string, unknown> & { id: string };
type Spec = { rows: (d: TenantData) => Row[]; texts: string[]; facets: string[] };

/** A run's actor: the customer when there is a conversation, else a customer or lead code in the subject, else the system. */
function withActor(d: TenantData): Row[] {
  const customerOf = new Map(d.conversations.map((c) => [c.runId, c.customer]));
  return (d.runs as Run[]).map((r) => ({ ...r, actor: customerOf.get(r.id) ?? r.subject.match(/\b(?:CUS|LEAD)-\d+/)?.[0] ?? "System" }));
}

const SPECS: Record<string, Spec> = {
  runs: { rows: (d) => withActor(d).sort((a, b) => ((a.startedAt as string) < (b.startedAt as string) ? 1 : -1)), texts: ["subject", "id", "agentId", "actor", "status"], facets: ["status", "agentId", "actor", "clusterId"] },
  escalations: { rows: (d) => withActor(d).filter((r) => (r.status === "escalated" || r.status === "blocked") && r.escalation), texts: ["subject", "id", "agentId"], facets: ["status", "agentId"] },
  audit: { rows: (d) => d.audit as unknown as Row[], texts: ["action", "detail"], facets: ["action", "criticality"] },
  "access-decisions": { rows: (d) => d.accessDecisions as unknown as Row[], texts: ["principal", "action", "resource", "reason", "ruleId"], facets: ["decision", "principal"] },
  documents: { rows: (d) => d.documents as unknown as Row[], texts: ["title", "type"], facets: ["sensitivity", "type", "extractionStatus"] },
};

const keep = (row: Row, filters: [string, Set<string>][], skip?: string) => filters.every(([f, values]) => f === skip || values.has(String(row[f])));

export function listPage(d: TenantData, name: string, url: URL) {
  const spec = SPECS[name];
  if (!spec) return null;
  const q = url.searchParams;
  const filters = spec.facets.filter((f) => q.get(f)).map((f): [string, Set<string>] => [f, new Set(q.get(f)!.split(","))]);
  const everything = spec.rows(d);
  let rows = everything.filter((r) => keep(r, filters));
  const [sortField, direction] = (q.get("sort") ?? "").split(":");
  if (sortField) rows = [...rows].sort((a, b) => (String(a[sortField] ?? "") < String(b[sortField] ?? "") ? -1 : 1) * (direction === "desc" ? -1 : 1));
  const size = Math.min(Number(q.get("limit") ?? PAGE), MOST);
  const position = q.get("around") ? rows.findIndex((r) => r.id === q.get("around")) : -1;
  const offset = position >= 0 ? Math.floor(position / size) * size : Number(q.get("offset") ?? 0);
  const words = (q.get("q") ?? "").toLowerCase().split(/\s+/).filter(Boolean);
  const positions: number[] = [];
  if (words.length) rows.forEach((r, i) => positions.length < MOST_MATCHES && words.every((w) => spec.texts.map((t) => String(r[t] ?? "")).join(" ").toLowerCase().includes(w)) && positions.push(i));
  const facets = Object.fromEntries(spec.facets.map((f) => {
    const counts: Record<string, number> = {};
    for (const r of everything) if (keep(r, filters, f)) counts[String(r[f])] = (counts[String(r[f])] ?? 0) + 1;
    return [f, counts];
  }));
  return { items: rows.slice(offset, offset + size), offset, total: rows.length, position: position >= 0 ? position : null, facets, matches: { total: positions.length, positions } };
}
