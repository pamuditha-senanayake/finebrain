// Sample living memory, built from the sample runs so the mock has one source of truth: each run becomes a trace,
// refunds made by hand in Stripe become outside traces, traces group into patterns, and drift and skill drafts are
// read off the patterns. The real version comes from the trace store (K16 to K19).
// Used by: seed/build.ts, memory-queries.ts. Uses: prng.ts, types.ts.
import type { AreaKey, DriftItem, ExtractedSkill, Pattern, PolicyCheck, Run, TraceSummary } from "@/contracts";
import { DAY, iso, Rng, SEED_NOW } from "../prng";
import type { MemoryData, TenantData } from "../types";

// Config
export const PATTERN_BUDGET = 50;
export const DRAFT_MIN_SUPPORT = 20;
const OUTSIDE_REFUNDS = 64;
const WEEK = 7 * DAY;
export const AREA_NAMES: Record<AreaKey, string> = {
  customer_care: "Customers", finance: "Money", legal: "Rules", people: "Staff",
  operations: "Operations", sales: "Sales", product: "Product", general: "Other",
};
const AREA_OF_SKILL: Record<string, AreaKey> = {
  "care-answer": "customer_care", "care-goodwill": "customer_care", "refund-standard": "customer_care", "reputation-reply": "customer_care",
  "incident-comms": "customer_care", "delivery-status": "customer_care", "billing-dunning": "finance", "billing-receivables": "finance",
  "billing-expenses": "finance", "compliance-readiness": "legal", "compliance-renewals": "legal", "sentinel-access": "legal",
  "scheduler-booking": "operations", "scheduler-notes": "operations", "onboarding-checklist": "operations", "quality-overnight": "operations",
  "librarian-freshness": "operations", "sales-qualify": "sales", "sales-quote": "sales", "web-content-update": "product", "insights-experiment": "product",
};
const OUTCOME: Record<Run["status"], string> = {
  succeeded: "Done", escalated: "Escalated to a person", failed: "Failed", blocked: "Blocked by a rule",
  awaiting_approval: "Waiting for approval", running: "Running",
};
const STRIPE_STEPS = ["Customer asks for a refund", "Person checks the order", "Person refunds in Stripe", "Customer told"];

// --- Traces

function traceOfRun(run: Run): TraceSummary {
  const surprise = run.status === "failed" || run.status === "blocked";
  // An escalated run is a case the policy did not allow on its own, so it sits outside the policy in force
  const check: PolicyCheck = run.status === "failed" ? "unknown" : run.status === "escalated" ? "outside" : "within";
  return {
    id: `tr-${run.id}`, area: AREA_OF_SKILL[run.skill.id] ?? "general", source: "finebrain", subject: run.subject,
    startedAt: run.startedAt, endedAt: run.endedAt, outcome: OUTCOME[run.status], patternId: null,
    match: surprise ? "surprise" : "normal", policyCheck: check, drift: [], runId: run.id,
  };
}

// Hand refunds in Stripe: late ones (past the 30-day window) grow in the recent weeks, which is the policy drift.
function outsideRefund(rng: Rng, index: number): TraceSummary {
  const days = index % 2 ? rng.int(31, 45) : rng.int(5, 30);
  const started = SEED_NOW - rng.int(1, 13 * 24) * 3_600_000;
  const refused = rng.chance(0.08);
  return {
    id: `tr-stripe-${index}`, area: "customer_care", source: "outside", subject: `Refund in Stripe · CUS-${2100 + index} · ${days} days`,
    startedAt: iso(started), endedAt: iso(started + 6 * 60_000), outcome: refused ? "Refund refused" : "Refunded by a person",
    patternId: null, match: "normal", policyCheck: days > 30 ? "outside" : "within", drift: [], runId: null,
  };
}

// --- Patterns

function weekOf(at: string) {
  return Math.floor((SEED_NOW - Date.parse(at)) / WEEK);
}

// The last two weeks are real counts. The ten before are sample history around them, near zero for late refunds.
function weekCounts(traces: TraceSummary[], rng: Rng, growing: boolean): number[] {
  const recent = [0, 1].map((w) => traces.filter((t) => weekOf(t.startedAt) === w).length);
  const usual = Math.round((recent[0] + recent[1]) / 2);
  const history = Array.from({ length: 10 }, () => (growing ? rng.int(0, 2) : Math.max(0, usual + rng.int(-2, 2))));
  return [...history, recent[1], recent[0]];
}

function patternOf(d: TenantData, rng: Rng, key: string, traces: TraceSummary[], areaTotal: number): Pattern {
  const first = traces[0];
  const skill = d.skills.find((s) => s.id === key.split("|")[1]);
  const steps = skill ? [...skill.steps.map((s) => s.text), first.outcome] : STRIPE_STEPS;
  const name = `${skill?.name ?? "Refund in Stripe"} · ${first.outcome.toLowerCase()}${first.policyCheck === "outside" ? ", past the window" : ""}`;
  return {
    id: `pt-${key.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`, area: first.area, name, steps, outcome: first.outcome,
    policyCheck: first.policyCheck, skillId: skill?.id ?? null, weekCounts: weekCounts(traces, rng, first.policyCheck === "outside"),
    share: Math.round((traces.length / areaTotal) * 100) / 100, exampleTraceIds: traces.slice(0, 5).map((t) => t.id),
  };
}

// Group by area + skill + outcome + policy check, keep each area inside its budget, and stamp each trace with its pattern.
function buildPatterns(d: TenantData, rng: Rng, traces: TraceSummary[]): Pattern[] {
  const skillOfRun = new Map(d.runs.map((r) => [r.id, r.skill.id]));
  const groups = new Map<string, TraceSummary[]>();
  for (const t of traces) {
    const skillId = t.runId ? skillOfRun.get(t.runId) : "stripe";
    const key = `${t.area}|${skillId}|${t.outcome}|${t.policyCheck}`;
    groups.set(key, [...(groups.get(key) ?? []), t]);
  }
  const sorted = [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
  const perArea = new Map<AreaKey, number>();
  const patterns: Pattern[] = [];
  for (const [key, group] of sorted) {
    const used = perArea.get(group[0].area) ?? 0;
    if (used >= PATTERN_BUDGET) continue;
    perArea.set(group[0].area, used + 1);
    const pattern = patternOf(d, rng, key, group, traces.filter((t) => t.area === group[0].area).length);
    group.forEach((t) => (t.patternId = pattern.id));
    patterns.push(pattern);
  }
  return patterns;
}

// --- Drift and skill drafts

// A succeeded run with a denied access decision acted without an allow: security drift, zero tolerance.
function securityDrifts(d: TenantData, traces: TraceSummary[]): DriftItem[] {
  const denied = new Set(d.accessDecisions.filter((a) => a.decision === "deny" && a.runId).map((a) => a.runId));
  const hits = traces.filter((t) => t.runId && denied.has(t.runId) && t.outcome === "Done");
  hits.forEach((t) => t.drift.push("security"));
  return hits.map((t) => ({
    id: `dr-sec-${t.runId}`, kind: "security", area: t.area, subject: { type: "agent", id: d.runs.find((r) => r.id === t.runId)!.agentId, name: t.subject },
    summary: "An action finished although its access check said deny", metric: { label: "Actions without an allow", usual: 0, latest: 1 },
    evidenceTraceIds: [t.id], state: "detected", fix: null, recheck: null, reopenedNote: null, raisedAt: t.startedAt,
  }));
}

function refundDrifts(traces: TraceSummary[], late: Pattern | undefined): DriftItem[] {
  const refunds = traces.filter((t) => t.runId && t.subject.startsWith("Refund request") && t.outcome !== "Done");
  const lateTraces = traces.filter((t) => t.patternId === late?.id);
  refunds.forEach((t) => t.drift.push("skill"));
  lateTraces.forEach((t) => t.drift.push("policy"));
  const usualLate = late ? [...late.weekCounts.slice(0, 10)].sort((a, b) => a - b)[5] : 0;
  return [
    { id: "dr-skill-refund-standard", kind: "skill", area: "customer_care", subject: { type: "skill", id: "refund-standard", name: "Refund inside policy" },
      summary: "Refunds follow the skill's steps less often", metric: { label: "Runs that follow the skill", usual: 0.91, latest: 0.62 },
      evidenceTraceIds: refunds.slice(0, 20).map((t) => t.id), state: "awaiting_approval", raisedAt: iso(SEED_NOW - 2 * DAY),
      fix: { summary: "Check the plan type before the refund step, as people now do", changeRequestId: null }, recheck: null, reopenedNote: null },
    { id: "dr-policy-refund-window", kind: "policy", area: "customer_care", subject: { type: "policy", id: "refund-window@v3", name: "Refund window" },
      summary: "People refund past the 30-day window more often", metric: { label: "Late hand refunds per week", usual: usualLate, latest: late?.weekCounts[11] ?? 0 },
      evidenceTraceIds: lateTraces.slice(0, 20).map((t) => t.id), state: "sent_to_l1", raisedAt: iso(SEED_NOW - DAY),
      fix: { summary: "Refund window: 30 to 45 days, from 1 December", changeRequestId: null }, recheck: null, reopenedNote: null },
  ];
}

// Patterns no skill covers, with enough support, become drafts. Same outcome share compares traces with the same steps;
// follow rate is that share in the latest week alone, the part the draft was not built from.
function skillDrafts(patterns: Pattern[], traces: TraceSummary[]): ExtractedSkill[] {
  return patterns.filter((p) => !p.skillId && p.outcome === "Refunded by a person").flatMap((p, i) => {
    const support = traces.filter((t) => t.patternId === p.id).length;
    const sameSteps = traces.filter((t) => t.source === "outside" && t.policyCheck === p.policyCheck);
    const latestSame = sameSteps.filter((t) => weekOf(t.startedAt) === 0);
    const latestJoined = latestSame.filter((t) => t.patternId === p.id).length;
    if (support < DRAFT_MIN_SUPPORT) return [];
    return [{
      id: `xs-${p.id}`, area: p.area, name: p.policyCheck === "outside" ? "Late refund approved by a person" : "Refund in Stripe within the window",
      patternId: p.id, steps: p.steps.map((title, j) => ({ activity: `act-${j + 1}`, title })), support,
      sameOutcomeShare: Math.round((support / sameSteps.length) * 100) / 100,
      followRate: Math.round((latestJoined / Math.max(1, latestSame.length)) * 100) / 100,
      state: i === 0 ? "draft" : "in_review", changeRequestId: null, createdAt: iso(SEED_NOW - (i + 1) * DAY),
    }];
  });
}

// Its own random stream, so adding memory never shifts the sample data seeded after it.
export function seedMemory(d: TenantData) {
  const rng = new Rng(`${d.tenant.id}-memory`);
  // Step 1: every run and every hand refund becomes a trace
  const traces = [...d.runs.map(traceOfRun), ...Array.from({ length: OUTSIDE_REFUNDS }, (_, i) => outsideRefund(rng, i))];
  // Step 2: traces group into patterns per area
  const patterns = buildPatterns(d, rng, traces);
  // Step 3: drift and skill drafts read the patterns
  const late = patterns.find((p) => !p.skillId && p.policyCheck === "outside" && p.outcome === "Refunded by a person");
  const hasRefunds = d.skills.some((s) => s.id === "refund-standard");
  const drifts = [...(hasRefunds ? refundDrifts(traces, late) : []), ...securityDrifts(d, traces)];
  const data: MemoryData = { traces: traces.sort((a, b) => (a.startedAt < b.startedAt ? 1 : -1)), patterns, drifts, skills: skillDrafts(patterns, traces) };
  d.memory = data;
}
