import { http, HttpResponse, delay } from "msw";
import type { OpName } from "./ops";
import { db, OpError, TENANTS } from "./db";
import { analytics, ask, overview, researchSnapshots, search } from "./queries";
import { generateSteps } from "./seed/build";
import type { TenantData } from "./types";

const LATENCY_MS = Number(process.env.NEXT_PUBLIC_MOCK_LATENCY_MS ?? 120);

type Params = Record<string, string | readonly string[] | undefined>;
type Getter = (d: TenantData, params: Params, url: URL) => unknown;

function str(v: string | readonly string[] | undefined) {
  return Array.isArray(v) ? v[0] : (v as string | undefined) ?? "";
}

function fail(e: unknown) {
  if (e instanceof OpError) return HttpResponse.json({ error: e.message }, { status: e.status });
  console.error(e);
  return HttpResponse.json({ error: e instanceof Error ? e.message : "Mock server error" }, { status: 500 });
}

const GETTERS: Record<string, Getter> = {
  tenant: (d) => d.tenant,
  clusters: (d) => d.clusters,
  humans: (d) => d.humans,
  agents: (d) => d.agents,
  "agents/:id": (d, p) => d.agents.find((a) => a.id === str(p.id)) ?? null,
  skills: (d, _p, url) => {
    const branch = url.searchParams.get("branch");
    return branch ? d.skills.filter((s) => s.branch === branch) : d.skills;
  },
  "skills/:id": (d, p) => d.skills.filter((s) => s.id === str(p.id)),
  policies: (d) => d.policies,
  "policies/:key": (d, p) => d.policies.filter((x) => x.key === str(p.key)).sort((a, b) => a.version - b.version),
  facts: (d) => d.facts,
  documents: (d) => d.documents,
  "filing-rules": (d) => d.filingRules,
  "access-rules": (d) => d.accessRules,
  sensors: (d) => d.sensors,
  "tracking-plan": (d) => d.trackingPlan,
  templates: (d) => d.templates,
  resolver: (d) => d.resolver,
  graph: (d) => d.graph,
  librarian: (d) => d.librarian,
  runs: (d, _p, url) => {
    const agentId = url.searchParams.get("agentId");
    const status = url.searchParams.get("status");
    const limit = Number(url.searchParams.get("limit") ?? 0);
    let out = d.runs;
    if (agentId) out = out.filter((r) => r.agentId === agentId);
    if (status) out = out.filter((r) => r.status === status);
    return limit ? out.slice(0, limit) : out;
  },
  "runs/:id": (d, p) => {
    const run = d.runs.find((r) => r.id === str(p.id));
    return run ? { ...run, steps: generateSteps(run, d) } : null;
  },
  conversations: (d) => d.conversations,
  "conversations/:id": (d, p) => d.conversations.find((c) => c.id === str(p.id)) ?? null,
  escalations: (d) => d.runs.filter((r) => (r.status === "escalated" || r.status === "blocked") && r.escalation),
  "access-decisions": (d, _p, url) => {
    const principal = url.searchParams.get("principal");
    const decision = url.searchParams.get("decision");
    return d.accessDecisions.filter((a) => (!principal || a.principal === principal) && (!decision || a.decision === decision));
  },
  branches: (d) => d.branches,
  commits: (d, _p, url) => {
    const branch = url.searchParams.get("branch");
    return (branch ? d.commits.filter((c) => c.branch === branch) : d.commits).slice().reverse();
  },
  "change-requests": (d) => d.changeRequests,
  "change-requests/:id": (d, p) => d.changeRequests.find((c) => c.id === str(p.id)) ?? null,
  approvals: (d) => d.approvals,
  "approvals/:id": (d, p) => d.approvals.find((a) => a.id === str(p.id)) ?? null,
  obligations: (d) => d.obligations,
  "evidence-requests": (d) => d.evidenceRequests,
  grants: (d) => d.grants,
  risks: (d) => d.risks,
  "readiness-rules": (d) => d.readinessRules,
  gaps: (d) => d.gaps,
  loops: (d) => d.loops,
  "loops/:id": (d, p) => d.loops.find((l) => l.id === str(p.id)) ?? null,
  experiments: (d) => d.experiments,
  activities: (d) => d.activities,
  audit: (d, _p, url) => {
    const corr = url.searchParams.get("correlation");
    const actor = url.searchParams.get("actor");
    const env = url.searchParams.get("env");
    const minCrit = Number(url.searchParams.get("minCriticality") ?? 0);
    return d.audit.filter((a) => (!corr || a.correlationId === corr) && (!actor || a.actor.kind === actor) && (!env || a.env === env) && a.criticality >= minCrit);
  },
  notifications: (d) => d.notifications,
  digest: (d) => d.digest,
  overview: (d) => overview(d, db.now()),
  analytics: (d) => analytics(d, db.now()),
  search: (d, _p, url) => search(d, url.searchParams.get("q") ?? ""),
  research: (d) => researchSnapshots(d, db.now()),
  clock: () => ({ now: new Date(db.now()).toISOString() }),
};

export const handlers = [
  http.get("*/api/tenants", async () => {
    await delay(LATENCY_MS);
    return HttpResponse.json(TENANTS);
  }),
  ...Object.entries(GETTERS).map(([path, getter]) =>
    http.get(`*/api/t/:tenant/${path}`, async ({ params, request }) => {
      await delay(LATENCY_MS);
      try {
        const d = db.tenant(str(params.tenant));
        const body = getter(d, params, new URL(request.url));
        if (body === null) return HttpResponse.json({ error: "Not found" }, { status: 404 });
        return HttpResponse.json(structuredClone(body));
      } catch (e) {
        return fail(e);
      }
    }),
  ),
  http.post("*/api/t/:tenant/ops/:op", async ({ params, request }) => {
    await delay(LATENCY_MS * 2);
    try {
      const persona = request.headers.get("x-persona") ?? "";
      const args = await request.json().catch(() => ({}));
      const result = db.run(str(params.tenant), str(params.op) as OpName, args, persona);
      return HttpResponse.json(structuredClone(result ?? { ok: true }));
    } catch (e) {
      return fail(e);
    }
  }),
  http.post("*/api/t/:tenant/ask", async ({ params, request }) => {
    await delay(LATENCY_MS * 4);
    try {
      const d = db.tenant(str(params.tenant));
      const persona = request.headers.get("x-persona") ?? "";
      const asker = d.humans.find((h) => h.id === persona);
      if (!asker) throw new OpError("Unknown persona", 401);
      const { question } = (await request.json()) as { question: string };
      return HttpResponse.json(ask(d, asker, question, db.now()));
    } catch (e) {
      return fail(e);
    }
  }),
  http.post("*/api/mock/reset", async () => {
    db.reset();
    return HttpResponse.json({ ok: true });
  }),
];
