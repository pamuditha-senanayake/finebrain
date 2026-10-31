import { z } from "zod";
import { IsoDate, VersionRef } from "./common";
import { TraceStep } from "./work";

// Living memory: brain areas, patterns, traces and drift (Docs/CB_Living_Memory_Architecture.md).
// Paths sit under /api/t/{tenant}/memory. Every shape here is what the page reads, never more.

// --- Areas

// The fixed domain list S2 already tags every item with (backend item_tags.py), so there is one list.
export const AreaKey = z.enum(["customer_care", "finance", "legal", "people", "operations", "sales", "product", "general"]);
export type AreaKey = z.infer<typeof AreaKey>;

export const DriftKind = z.enum(["skill", "policy", "security"]);
export type DriftKind = z.infer<typeof DriftKind>;

export const DriftCounts = z.object({ skill: z.number().int(), policy: z.number().int(), security: z.number().int() });
export type DriftCounts = z.infer<typeof DriftCounts>;

export const MemoryArea = z.object({
  key: AreaKey,
  name: z.string(),
  enabled: z.boolean(),
  traces7d: z.number().int(),
  tracesTotal: z.number().int(),
  patterns: z.number().int(),
  patternBudget: z.number().int(),
  skills: z.object({ authored: z.number().int(), fromTraces: z.number().int() }),
  drift: DriftCounts,
  surprises: z.number().int(),
  outsidePolicy: z.number().int(),
});
export type MemoryArea = z.infer<typeof MemoryArea>;

export const MemoryMap = z.object({
  tenantId: z.string(),
  asOf: IsoDate,
  isSample: z.boolean(),
  areas: z.array(MemoryArea),
  totals: z.object({ traces7d: z.number().int(), patterns: z.number().int(), drift: DriftCounts, surprises: z.number().int() }),
});
export type MemoryMap = z.infer<typeof MemoryMap>;

// --- Patterns and drift

export const PolicyCheck = z.enum(["within", "outside", "unknown"]);
export type PolicyCheck = z.infer<typeof PolicyCheck>;

// One typical way work goes in an area. weekCounts holds the last 12 weeks, oldest first.
export const Pattern = z.object({
  id: z.string(),
  area: AreaKey,
  name: z.string(),
  steps: z.array(z.string()),
  outcome: z.string(),
  policyCheck: PolicyCheck,
  skillId: z.string().nullable(),
  weekCounts: z.array(z.number().int()).length(12),
  share: z.number(),
  exampleTraceIds: z.array(z.string()).max(5),
});
export type Pattern = z.infer<typeof Pattern>;

// Where a drift stands (Docs/CB_Living_Memory_Architecture.md section 8b). A rejected or failed fix returns to detected.
export const DriftState = z.enum(["detected", "sent_to_l1", "awaiting_approval", "approved", "resolved"]);
export type DriftState = z.infer<typeof DriftState>;

export const DriftItem = z.object({
  id: z.string(),
  kind: DriftKind,
  area: AreaKey,
  subject: z.object({ type: z.enum(["skill", "policy", "agent"]), id: z.string(), name: z.string() }),
  summary: z.string(),
  metric: z.object({ label: z.string(), usual: z.number(), latest: z.number() }),
  evidenceTraceIds: z.array(z.string()),
  state: DriftState,
  // The draft fix an L1 user decides on. Security drift has none: it goes to L1 as an incident.
  fix: z.object({ summary: z.string(), changeRequestId: z.string().nullable() }).nullable(),
  // The 14-day watch after a fix goes live; reopenedNote says why an approved fix did not hold.
  recheck: z.object({ until: IsoDate, result: z.enum(["watching", "dropped", "still_drifting"]) }).nullable(),
  reopenedNote: z.string().nullable(),
  raisedAt: IsoDate,
});
export type DriftItem = z.infer<typeof DriftItem>;

export const AreaDetail = z.object({ area: MemoryArea, patterns: z.array(Pattern), drifts: z.array(DriftItem) });
export type AreaDetail = z.infer<typeof AreaDetail>;

// --- Traces

export const TraceSummary = z.object({
  id: z.string(),
  area: AreaKey,
  source: z.enum(["finebrain", "outside"]),
  subject: z.string(),
  startedAt: IsoDate,
  endedAt: IsoDate.nullable(),
  outcome: z.string(),
  patternId: z.string().nullable(),
  match: z.enum(["normal", "surprise"]),
  policyCheck: PolicyCheck,
  drift: z.array(DriftKind),
  runId: z.string().nullable(),
});
export type TraceSummary = z.infer<typeof TraceSummary>;

export const TraceFlag = z.enum(["surprise", "outside_policy", "drift"]);
export type TraceFlag = z.infer<typeof TraceFlag>;

export const TracePage = z.object({ items: z.array(TraceSummary), nextCursor: z.string().nullable(), total: z.number().int() });
export type TracePage = z.infer<typeof TracePage>;

export const TraceAccess = z.object({
  action: z.string(),
  principal: z.string(),
  onBehalfOf: z.string().nullable(),
  decision: z.enum(["allow", "deny"]),
  ruleId: z.string(),
  reason: z.string(),
  latencyMs: z.number(),
});
export type TraceAccess = z.infer<typeof TraceAccess>;

export const TracePolicy = z.object({ id: z.string(), name: z.string(), version: z.number().int(), validFrom: IsoDate, validTo: IsoDate.nullable() });
export type TracePolicy = z.infer<typeof TracePolicy>;

// The whole trace, start to end. why holds one short line per judgment step.
export const TraceDetail = TraceSummary.extend({
  inputRef: z.string(),
  steps: z.array(TraceStep),
  policies: z.array(TracePolicy),
  skill: VersionRef.nullable(),
  skillName: z.string().nullable().optional(), // the skill's name in Studio
  access: z.array(TraceAccess),
  why: z.array(z.string()),
});
export type TraceDetail = z.infer<typeof TraceDetail>;

// --- Skills from traces

export const ExtractedSkill = z.object({
  id: z.string(),
  area: AreaKey,
  name: z.string(),
  patternId: z.string(),
  steps: z.array(z.object({ activity: z.string(), title: z.string() })),
  support: z.number().int(),
  sameOutcomeShare: z.number(),
  followRate: z.number(),
  state: z.enum(["draft", "in_review", "approved", "rejected"]),
  changeRequestId: z.string().nullable(),
  createdAt: IsoDate,
});
export type ExtractedSkill = z.infer<typeof ExtractedSkill>;
