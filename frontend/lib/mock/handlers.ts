import { http, HttpResponse, delay, passthrough } from "msw";
import { realTenants } from "@/lib/flags";
import type { OpName } from "./ops";
import { db, OpError, TENANTS } from "./db";
import { analytics, ask, overview, researchSnapshots, search } from "./queries";
import { listPage } from "./lists";
import { generateSteps } from "./seed/build";
import { chat, historyOf, reviewReply } from "./studio/chat";
import { StudioError, detail, healthOf, scopeOf, summaries, workflowsUsingTool } from "./studio/engine";
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
  "access-homes": (d) => Object.fromEntries(d.studio.items.filter((i) => i.workflowId).map((i) => [i.id, i.workflowId])),
  "access-tiers": () => [
    { tier: "L1", reads: ["public", "internal", "confidential", "restricted"] },
    { tier: "L2", reads: ["public", "internal", "confidential", "restricted"] },
    { tier: "L3", reads: ["public", "internal", "confidential"] },
  ],
  sensors: (d) => d.sensors,
  "tracking-plan": (d) => d.trackingPlan,
  templates: (d) => d.templates,
  resolver: (d) => d.resolver,
  graph: (d) => d.graph,
  librarian: (d) => d.librarian,
  "lists/:name": (d, p, url) => listPage(d, str(p.name), url) ?? [],
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
  trends: (d) => d.trends,
  overview: (d) => overview(d, db.now()),
  analytics: (d) => analytics(d, db.now()),
  search: (d, _p, url) => search(d, url.searchParams.get("q") ?? ""),
  research: (d) => researchSnapshots(d, db.now()),
  clock: () => ({ now: new Date(db.now()).toISOString() }),
  "studio/workflows": (d) => summaries(d),
  "studio/map": (d) => {
    const o = overview(d, db.now());
    const sums = summaries(d);
    return {
      clusters: d.clusters.map((c) => {
        const k = o.kpis.find((x) => x.clusterId === c.id);
        return { id: c.id, name: c.name, description: c.description, status: c.status, dri: c.dri, health: c.health, kpi: c.status === "active" && k ? { runs24h: k.runs24h, autonomyRate: k.autonomyRate, escalationRate: k.escalationRate, costPerResolvedUsd: k.costPerResolvedUsd, moneyAtStakeMinor: k.moneyAtStakeMinor, openRisks: k.openRisks } : null };
      }),
      workflows: d.studio.workflows.map((w) => ({
        id: w.id, name: w.name, description: w.description, clusterId: w.clusterId, status: w.status, criticality: w.criticality, dri: w.dri,
        health: sums.find((x) => x.id === w.id)?.health ?? { breaks: 0, warnings: 0 },
        items: scopeOf(d.studio, w).map((i) => ({ id: i.id, kind: i.kind, name: i.name, description: i.description, status: i.status, shared: i.kind === "tool" && workflowsUsingTool(d.studio, i.id).length > 1 })),
      })),
    };
  },
  "studio/workflows/:id": (d, p) => detail(d, str(p.id)),
  "studio/workflows/:id/health": (d, p) => {
    const wf = d.studio.workflows.find((w) => w.id === str(p.id));
    return wf ? healthOf(d, wf) : null;
  },
  "studio/tools": (d) => d.studio.items.filter((i) => i.kind === "tool").map((t) => ({ tool: t, workflows: workflowsUsingTool(d.studio, t.id).map((w) => ({ id: w.id, name: w.name })) })),
  "studio/revisions": (d, _p, url) => {
    const target = url.searchParams.get("target");
    const workflow = url.searchParams.get("workflow");
    if (target) return historyOf(d, target);
    return d.studio.revisions.filter((r) => !workflow || r.workflowId === workflow).sort((a, b) => (a.at < b.at ? 1 : -1)).slice(0, 200);
  },
  "studio/pending": (d) =>
    d.studio.pending.map((p) => {
      const cr = d.changeRequests.find((c) => c.id === p.changeRequestId);
      return p.status === "awaiting_approval" && cr && ["rejected", "expired"].includes(cr.status) ? { ...p, status: "rejected" as const } : p;
    }),
};

function studioPost(path: string, fn: (d: TenantData, persona: string, body: unknown) => unknown) {
  return http.post(`*/api/t/:tenant/studio/${path}`, async ({ params, request }) => {
    await delay(LATENCY_MS * 3);
    try {
      const d = db.tenant(str(params.tenant));
      const persona = request.headers.get("x-persona") ?? "";
      if (!d.humans.some((h) => h.id === persona)) throw new OpError("Unknown persona", 401);
      return HttpResponse.json(structuredClone(fn(d, persona, await request.json().catch(() => ({})))) as Record<string, unknown>);
    } catch (e) {
      if (e instanceof StudioError) return HttpResponse.json({ error: e.message }, { status: e.status });
      return fail(e);
    }
  });
}

export const handlers = [
  // Real tenants go to the backend untouched; this must stay the first handler so it wins.
  ...[...realTenants].map((tenantId) => http.all(`*/api/t/${tenantId}/*`, () => passthrough())),
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
      const { question, page } = (await request.json()) as { question: string; page?: { path: string; scope: "page" | "system" } };
      return HttpResponse.json(ask(d, asker, question, db.now(), page));
    } catch (e) {
      return fail(e);
    }
  }),
  // Demo tenants file an upload straight into the Library; the real brain reads and indexes it first.
  http.post("*/api/t/:tenant/documents", async ({ params, request }) => {
    await delay(LATENCY_MS * 3);
    try {
      const d = db.tenant(str(params.tenant));
      const file = (await request.formData()).get("file") as File | null;
      if (!file) throw new OpError("No file", 400);
      const doc = { id: `doc-up-${Date.now().toString(36)}`, tenantId: d.tenant.id, clusterId: d.clusters[0]?.id ?? "", title: file.name.replace(/\.[^.]+$/, ""), source: "Lisena upload", type: file.name.split(".").pop() ?? "file", sensitivity: "internal" as const, extractionStatus: "done" as const, linkedFacts: [], retentionDays: 365, filingRule: "uploads", uploadedBy: request.headers.get("x-persona") ?? "", uploadedAt: new Date(db.now()).toISOString(), sizeKb: Math.max(1, Math.round(file.size / 1024)), personalData: false };
      d.documents.unshift(doc);
      return HttpResponse.json(doc, { status: 202 });
    } catch (e) {
      return fail(e);
    }
  }),
  studioPost("chat", (d, persona, body) => chat(d, d.humans.find((h) => h.id === persona)!, body as Parameters<typeof chat>[2])),
  studioPost("review", (d, persona, body) => {
    const { input, workflowId } = body as { input: Parameters<typeof reviewReply>[2]; workflowId: string };
    return reviewReply(d, d.humans.find((h) => h.id === persona)!, input, workflowId);
  }),
  http.post("*/api/mock/reset", async () => {
    db.reset();
    return HttpResponse.json({ ok: true });
  }),
];
