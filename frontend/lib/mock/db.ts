import type { Actor, Approval, ChangeRequest, Run } from "@/contracts";
import { OPS, OpError, type Ctx, type OpName } from "./ops";
import { HOUR, Rng, SEED_NOW, iso } from "./prng";
import { realTenants } from "@/lib/flags";
import { buildFinebase, buildScale } from "./seed/build";
import type { TenantData } from "./types";

export type LiveEvent = { type: string; tenantId: string; at: string; resources: string[]; summary: string };
type JournalEntry = { tenantId: string; op: OpName; args: unknown; actorId: string; at: number };

const JOURNAL_KEY = "cb.mock.journal.v1";
export const TENANTS = [
  { id: "demo-fbl", name: "demo-fbl", isScaleDemo: false },
  { id: "scale", name: "Scale Demo", isScaleDemo: true },
  { id: "finebase-hq", name: "Finebase HQ", isScaleDemo: false }, // real backend, never built from mock data
];

function readJournal(): JournalEntry[] {
  try {
    return typeof localStorage === "undefined" ? [] : (JSON.parse(localStorage.getItem(JOURNAL_KEY) ?? "[]") as JournalEntry[]);
  } catch {
    return [];
  }
}

function writeJournal(entries: JournalEntry[]) {
  try {
    if (typeof localStorage !== "undefined") localStorage.setItem(JOURNAL_KEY, JSON.stringify(entries));
  } catch {
    // Storage can be full or blocked. The demo still works for this session.
  }
}

class MockDb {
  private tenants = new Map<string, TenantData>();
  private bootWall = Date.now();
  private clockOverride: number | null = null;
  private listeners = new Set<(e: LiveEvent) => void>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private liveCounter = 0;
  private tick = 0;
  private rng = new Rng("live-stream");

  now() {
    return this.clockOverride ?? SEED_NOW + (Date.now() - this.bootWall);
  }

  tenant(tenantId: string): TenantData {
    let d = this.tenants.get(tenantId);
    if (!d) {
      if (!TENANTS.some((t) => t.id === tenantId) || realTenants.has(tenantId)) throw new OpError(`Unknown tenant ${tenantId}`, 404);
      d = tenantId === "scale" ? buildScale() : buildFinebase();
      this.tenants.set(tenantId, d);
      for (const entry of readJournal().filter((e) => e.tenantId === tenantId)) {
        this.clockOverride = entry.at;
        try {
          this.apply(d, entry.op, entry.args, entry.actorId);
        } catch {
          // A journal entry that no longer applies is skipped, never fatal.
        } finally {
          this.clockOverride = null;
        }
      }
    }
    return d;
  }

  private actor(d: TenantData, actorId: string): Actor {
    const h = d.humans.find((x) => x.id === actorId);
    if (!h) throw new OpError("Unknown persona. Pick one in the role switcher.", 401);
    return { kind: "human", id: h.id, name: h.name };
  }

  private apply(d: TenantData, op: OpName, args: unknown, actorId: string) {
    const ctx: Ctx = { now: this.now(), actor: this.actor(d, actorId) };
    const fn = OPS[op] as (d: TenantData, ctx: Ctx, args: unknown) => unknown;
    return fn(d, ctx, args ?? {});
  }

  run(tenantId: string, op: OpName, args: unknown, actorId: string) {
    if (!(op in OPS)) throw new OpError(`Unknown operation ${op}`, 404);
    const d = this.tenant(tenantId);
    const at = this.now();
    const result = this.apply(d, op, args, actorId);
    writeJournal([...readJournal(), { tenantId, op, args, actorId, at }]);
    this.emit({ type: `op.${op}`, tenantId, at: iso(at), resources: ["*"], summary: op });
    return result;
  }

  reset() {
    writeJournal([]);
    this.tenants.clear();
    this.emit({ type: "reset", tenantId: "*", at: iso(this.now()), resources: ["*"], summary: "Demo data reset" });
  }

  subscribe(fn: (e: LiveEvent) => void) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(e: LiveEvent) {
    for (const fn of this.listeners) fn(e);
  }

  startStream(intervalMs = 5000) {
    if (this.timer) return;
    this.timer = setInterval(() => this.streamTick(), intervalMs);
  }

  stopStream() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  /** Mock event stream: new runs, status changes and, now and then, an approval. Uses its own id space so journal replay stays deterministic. */
  private streamTick() {
    this.tick += 1;
    const now = this.now();
    for (const d of this.tenants.values()) {
      const working = d.agents.filter((a) => a.status === "working" && a.kind === "worker");
      const resources = new Set<string>(["runs", "agents", "overview"]);
      for (let i = 0; i < (d.tenant.isScaleDemo ? 6 : 1); i++) {
        const agent = working.length ? this.rng.pick(working) : null;
        if (!agent) break;
        this.liveCounter += 1;
        const run: Run = {
          id: `live-${this.liveCounter}`, tenantId: d.tenant.id, clusterId: agent.clusterId, agentId: agent.id, skill: agent.skills[0] ?? { id: "none", version: 1, branch: "main" }, env: "production",
          subject: `Live · ${agent.name.replace(" Agent", "")} task ${this.liveCounter}`, status: "running", startedAt: iso(now), endedAt: null, escalation: null, conversationId: null,
          costTokens: this.rng.int(600, 6000), costUsd: 0.01, latencyMs: 0, humanTouch: false, failureClass: null,
        };
        d.runs.unshift(run);
      }
      for (const r of d.runs.slice(0, 40)) {
        if (r.status === "running" && r.id.startsWith("live-") && now - Date.parse(r.startedAt) > 12_000) {
          r.status = this.rng.chance(0.94) ? "succeeded" : "escalated";
          r.endedAt = iso(now);
          r.latencyMs = now - Date.parse(r.startedAt);
          if (r.status === "escalated") {
            r.humanTouch = true;
            r.escalation = { reason: "Confidence below threshold", risk: "low", since: iso(now), assignee: null, criticality: 2 };
          }
        }
      }
      const flip = this.rng.pick(d.agents.filter((a) => a.kind === "worker"));
      if (flip && flip.status !== "blocked" && flip.status !== "error") {
        flip.status = flip.status === "working" ? "idle" : "working";
        flip.workKind = flip.status === "working" ? this.rng.pick(["retrieval", "judgment", "tool"] as const) : null;
        flip.queueDepth = flip.status === "working" ? this.rng.int(1, 6) : 0;
      }
      if (this.tick % 18 === 0) {
        this.liveApproval(d, now);
        resources.add("approvals").add("notifications").add("change-requests");
      }
      this.emit({ type: "stream.tick", tenantId: d.tenant.id, at: iso(now), resources: [...resources], summary: "New runs and status changes" });
    }
  }

  private liveApproval(d: TenantData, now: number) {
    this.liveCounter += 1;
    const id = `live-${this.liveCounter}`;
    const drafter: Actor = { kind: "agent", id: d.agents.find((a) => a.kind === "supervisor")?.id ?? "a-quality", name: "Quality Supervisor" };
    const cr: ChangeRequest = {
      id: `cr-${id}`, tenantId: d.tenant.id, title: `FAQ wording fix ${this.liveCounter}`, kind: "fix", fromBranch: `sandbox/${id}`, toBranch: "main", commits: [],
      plainDiff: ["Clarify an answer that customers asked about twice today."], changes: [{ op: "modify", nodeType: "skill", nodeId: "care-answer", label: "Answer product question", field: "steps", before: "old wording", after: "new wording" }],
      impactPreview: { runsReplayed: 60, decisionsChanged: 2, predictedRisk: "low", summary: "2 of 60 replayed answers change wording.", examples: [] },
      tests: { suite: "eval-care-answer", total: 24, passed: 24, failed: 0, passK: 0.9, k: 8, ranAt: iso(now) }, approvalId: `apr-${id}`, status: "awaiting_approval", criticality: 2,
      criticalityReasons: ["skill step edit starts at C2"], drafter, dri: d.humans.find((h) => h.tier === "L2")?.id ?? "", clusters: [d.clusters[0].id], createdAt: iso(now), mergedAt: null, coolingUntil: null, correlationId: id,
    };
    const ap: Approval = {
      id: `apr-${id}`, tenantId: d.tenant.id, subject: { kind: "change_request", id: cr.id }, title: cr.title, summary: cr.plainDiff[0], criticality: 2, requiredApprovers: { tier: "L2", count: 1, roles: [] },
      votes: [], dueAt: iso(now + 72 * HOUR), createdAt: iso(now), status: "pending", delegatedTo: null, dri: cr.dri, drafter, evidence: [], correlationId: id,
    };
    d.changeRequests.unshift(cr);
    d.approvals.unshift(ap);
  }
}

export const db = new MockDb();
export { OpError };
