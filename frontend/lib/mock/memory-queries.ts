// Answers for the living memory paths: the map, one area, the trace list and one trace, drift, and skill drafts.
// Every answer is read off d.memory and the sample runs, so the page and the seed never disagree.
// Used by: handlers.ts, tests/unit/memory.test.ts. Uses: seed/memory.ts, seed/build.ts (generateSteps), types.ts.
import type { AreaDetail, AreaKey, DriftItem, MemoryArea, MemoryMap, TraceDetail, TraceFlag, TracePage, TracePolicy, TraceStep, TraceSummary } from "@/contracts";
import { AreaKey as AreaKeys } from "@/contracts";
import { generateSteps } from "./seed/build";
import { AREA_NAMES, PATTERN_BUDGET } from "./seed/memory";
import type { TenantData } from "./types";

// Config
const PAGE_SIZE = 25;
const WEEK_MS = 7 * 86_400_000;

// --- Map and areas

function openDrifts(d: TenantData, key: AreaKey) {
  return d.memory.drifts.filter((x) => x.area === key && x.state !== "resolved");
}

function areaOf(d: TenantData, key: AreaKey, now: number): MemoryArea {
  const traces = d.memory.traces.filter((t) => t.area === key);
  const recent = traces.filter((t) => now - Date.parse(t.startedAt) < WEEK_MS);
  const drifts = openDrifts(d, key);
  const skillIds = new Set(d.memory.patterns.filter((p) => p.area === key && p.skillId).map((p) => p.skillId));
  return {
    // Every area is on in the sample workspace; setup turns areas off for a real company
    key, name: AREA_NAMES[key], enabled: true, traces7d: recent.length, tracesTotal: traces.length,
    patterns: d.memory.patterns.filter((p) => p.area === key).length, patternBudget: PATTERN_BUDGET,
    skills: { authored: skillIds.size, fromTraces: d.memory.skills.filter((s) => s.area === key).length },
    drift: { skill: drifts.filter((x) => x.kind === "skill").length, policy: drifts.filter((x) => x.kind === "policy").length, security: drifts.filter((x) => x.kind === "security").length },
    surprises: recent.filter((t) => t.match === "surprise").length, outsidePolicy: recent.filter((t) => t.policyCheck === "outside").length,
  };
}

export function memoryMap(d: TenantData, now: number): MemoryMap {
  const areas = AreaKeys.options.map((key) => areaOf(d, key, now));
  const sum = (pick: (a: MemoryArea) => number) => areas.reduce((total, a) => total + pick(a), 0);
  return {
    tenantId: d.tenant.id, asOf: new Date(now).toISOString(), isSample: true, areas,
    totals: {
      traces7d: sum((a) => a.traces7d), patterns: sum((a) => a.patterns), surprises: sum((a) => a.surprises),
      drift: { skill: sum((a) => a.drift.skill), policy: sum((a) => a.drift.policy), security: sum((a) => a.drift.security) },
    },
  };
}

export function areaDetail(d: TenantData, key: string, now: number): AreaDetail | null {
  const parsed = AreaKeys.safeParse(key);
  if (!parsed.success) return null;
  const patterns = d.memory.patterns.filter((p) => p.area === parsed.data).sort((a, b) => b.share - a.share);
  return { area: areaOf(d, parsed.data, now), patterns, drifts: openDrifts(d, parsed.data) };
}

// --- Traces

function hasFlag(t: TraceSummary, flag: TraceFlag | null) {
  if (flag === "surprise") return t.match === "surprise";
  if (flag === "outside_policy") return t.policyCheck === "outside";
  if (flag === "drift") return t.drift.length > 0;
  return true;
}

// The cursor is the offset of the next page; traces are already newest first.
export function tracePage(d: TenantData, area: string | null, flag: string | null, cursor: string | null): TracePage {
  const matching = d.memory.traces.filter((t) => (!area || t.area === area) && hasFlag(t, flag as TraceFlag | null));
  const start = Number(cursor ?? 0) || 0;
  const items = matching.slice(start, start + PAGE_SIZE);
  return { items, nextCursor: start + PAGE_SIZE < matching.length ? String(start + PAGE_SIZE) : null, total: matching.length };
}

// The policy versions in force when the trace started: what the work was really held to.
function policiesAt(d: TenantData, keys: string[], at: string): TracePolicy[] {
  return keys.flatMap((key) => {
    const version = d.policies.find((p) => p.key === key && p.validFrom <= at && (!p.validTo || p.validTo > at));
    return version ? [{ id: version.id, name: version.name, version: version.version, validFrom: version.validFrom, validTo: version.validTo }] : [];
  });
}

function stripeSteps(t: TraceSummary): TraceStep[] {
  const titles = ["Customer asks for a refund", "Person checks the order", "Person refunds in Stripe", "Customer told"];
  return titles.map((title, idx) => ({
    id: `${t.id}-s${idx}`, idx, kind: idx === 2 ? "tool" : "human", title, decision: idx === 2 ? t.outcome : "Done",
    reason: idx === 1 ? t.subject.split(" · ").pop() + " since purchase" : "", durationMs: 60_000, at: t.startedAt,
    facts: [], access: null, gate: null, tool: idx === 2 ? "stripe.refund" : null, templateFields: [], costTokens: 0,
  }));
}

export function traceDetail(d: TenantData, id: string): TraceDetail | null {
  const t = d.memory.traces.find((x) => x.id === id);
  if (!t) return null;
  const run = t.runId ? d.runs.find((r) => r.id === t.runId) : undefined;
  const steps = run ? generateSteps(run, d) : stripeSteps(t);
  const skill = run ? d.skills.find((s) => s.id === run.skill.id) : undefined;
  const access = d.accessDecisions.filter((a) => a.runId && a.runId === t.runId)
    .map((a) => ({ action: a.action, principal: a.principal, onBehalfOf: a.onBehalfOf, decision: a.decision, ruleId: a.ruleId, reason: a.reason, latencyMs: a.latencyMs }));
  return {
    ...t, inputRef: run?.conversationId ?? `stripe:${t.id}`, steps, access,
    policies: policiesAt(d, skill?.policies ?? ["refund-window"], t.startedAt), skill: run ? run.skill : null,
    why: steps.filter((s) => s.kind === "judgment" && s.reason).map((s) => s.reason),
  };
}

// --- Drift and skill drafts

export function driftList(d: TenantData, area: string | null, kind: string | null): DriftItem[] {
  return d.memory.drifts.filter((x) => (!area || x.area === area) && (!kind || x.kind === kind));
}

export function skillDraftList(d: TenantData) {
  return d.memory.skills;
}
