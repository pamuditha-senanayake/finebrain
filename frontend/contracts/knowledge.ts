import { z } from "zod";
import { Criticality, IsoDate, NodeType, Sensitivity, Tier, VersionRef } from "./common";

export const SkillStep = z.object({
  id: z.string(),
  kind: z.enum(["judgment", "tool", "retrieval", "quality_gate"]),
  text: z.string(),
  tool: z.string().nullable(),
});
export type SkillStep = z.infer<typeof SkillStep>;

export const SkillHealth = z.object({
  taskSuccess: z.number(),
  consistencyPassK: z.number(),
  k: z.number().int(),
  conformance: z.number(),
});
export type SkillHealth = z.infer<typeof SkillHealth>;

export const Skill = z.object({
  id: z.string(),
  tenantId: z.string(),
  name: z.string(),
  version: z.number().int(),
  branch: z.string(),
  status: z.enum(["draft", "active", "deprecated"]),
  clusterId: z.string(),
  trigger: z.string(),
  inputs: z.array(z.string()),
  steps: z.array(SkillStep),
  tools: z.array(z.string()),
  policies: z.array(z.string()),
  requiredCapabilities: z.array(z.string()),
  outputs: z.array(z.string()),
  templateFields: z.array(z.string()),
  evalSuite: z.object({ id: z.string(), cases: z.number().int(), passRate: z.number() }),
  health: SkillHealth,
  agentIds: z.array(z.string()),
  dri: z.string(),
  updatedAt: IsoDate,
  origin: z.enum(["authored", "skillify", "overnight"]),
});
export type Skill = z.infer<typeof Skill>;

export const FreshnessSignals = z.object({
  intervalClosed: z.boolean(),
  driftPointAt: IsoDate.nullable(),
  conformance: z.number(),
  conflictingEvidence: z.number().int(),
  outdatedRelianceRate: z.number(),
});
export type FreshnessSignals = z.infer<typeof FreshnessSignals>;

export const PolicyRule = z.object({
  kind: z.string(),
  params: z.record(z.string(), z.union([z.string(), z.number(), z.boolean()])),
});

export const Policy = z.object({
  id: z.string(),
  key: z.string(),
  tenantId: z.string(),
  name: z.string(),
  version: z.number().int(),
  branch: z.string(),
  clusterId: z.string(),
  statement: z.string(),
  rule: PolicyRule,
  criticality: Criticality,
  validFrom: IsoDate,
  validTo: IsoDate.nullable(),
  recordedAt: IsoDate,
  supersededBy: z.string().nullable(),
  evidence: z.array(z.string()),
  freshness: FreshnessSignals,
  dependents: z.array(z.object({ type: NodeType.or(z.literal("web_page")), id: z.string(), label: z.string() })),
  dri: z.string(),
});
export type Policy = z.infer<typeof Policy>;

export const Evidence = z.object({
  documentId: z.string(),
  page: z.number().int().nullable(),
  quote: z.string(),
});

export const Fact = z.object({
  id: z.string(),
  tenantId: z.string(),
  clusterId: z.string(),
  statement: z.string(),
  subject: z.string(),
  value: z.string(),
  validFrom: IsoDate,
  validTo: IsoDate.nullable(),
  recordedAt: IsoDate,
  evidence: z.array(Evidence),
  verifiedBy: z.string().nullable(),
  status: z.enum(["verified", "unverified", "stale", "conflicted", "superseded"]),
  sensitivity: Sensitivity,
  dependents: z.array(z.object({ type: z.string(), id: z.string(), label: z.string() })),
  /** The core field dictionary (step 13d): every fact read into the same five fields; a value that fits none is a named extra. */
  core: z.object({ who: z.string().nullable(), what: z.string().nullable(), when: z.string().nullable(), amount: z.string().nullable(), outcome: z.string().nullable() }).nullable().optional(),
  extra: z.record(z.string(), z.string()).nullable().optional(),
});
export type Fact = z.infer<typeof Fact>;

/** What removing a document did, layer by layer (step 10). */
export const ForgetReceipt = z.object({
  mode: z.enum(["retire", "erase"]),
  at: IsoDate,
  by: z.string(),
  layers: z.array(z.object({ layer: z.string(), result: z.enum(["cleared", "kept", "nothing"]), note: z.string() })),
  verified: z.boolean(),
  failed: z.array(z.string()),
});
export type ForgetReceipt = z.infer<typeof ForgetReceipt>;

/** The review before a document is removed: what depends on it, the level, and the next warning. */
export const ForgetReview = z.object({
  requestId: z.string(),
  documentId: z.string(),
  mode: z.enum(["retire", "erase"]),
  level: z.number().int(),
  status: z.enum(["review", "done", "incomplete"]),
  dependents: z.array(z.object({ type: z.string(), id: z.string(), label: z.string() })),
  confirmationsLeft: z.number().int(),
  warning: z.string(),
  receipt: ForgetReceipt.nullable(),
});
export type ForgetReview = z.infer<typeof ForgetReview>;

export const Document = z.object({
  id: z.string(),
  tenantId: z.string(),
  clusterId: z.string(),
  title: z.string(),
  source: z.string(),
  type: z.string(),
  sensitivity: Sensitivity,
  extractionStatus: z.enum(["pending", "extracting", "done", "failed", "retired", "erased"]),
  linkedFacts: z.array(z.string()),
  retentionDays: z.number().int(),
  filingRule: z.string(),
  uploadedBy: z.string(),
  uploadedAt: IsoDate,
  sizeKb: z.number().int(),
  personalData: z.boolean(),
  receipt: ForgetReceipt.nullish(),
  /** Step 14: its place in a version chain, and the newer version that replaced it. */
  version: z.number().int().nullish(),
  replacedBy: z.string().nullish(),
});
export type Document = z.infer<typeof Document>;

export const FilingRule = z.object({
  id: z.string(),
  match: z.string(),
  clusterId: z.string(),
  type: z.string(),
  sensitivity: Sensitivity,
  retentionDays: z.number().int(),
});
export type FilingRule = z.infer<typeof FilingRule>;

export const AccessRule = z.object({
  id: z.string(),
  tenantId: z.string(),
  name: z.string(),
  appliesTo: z.string(),
  requiresRoles: z.array(z.string()),
  requiresAttributes: z.record(z.string(), z.string()),
  requiresCapability: z.string().nullable(),
  sensitivity: Sensitivity,
  description: z.string(),
});
export type AccessRule = z.infer<typeof AccessRule>;

/** Which data each tier reads. */
export const TierReads = z.object({ tier: Tier, reads: z.array(Sensitivity) });
export type TierReads = z.infer<typeof TierReads>;

/** The answer to "would this be allowed?": nothing runs and nothing is logged. */
export const AccessCheckResult = z.object({ allow: z.boolean(), ruleId: z.string(), reason: z.string(), tier: Tier, effectiveTier: Tier });
export type AccessCheckResult = z.infer<typeof AccessCheckResult>;

export const Sensor = z.object({
  id: z.string(),
  tenantId: z.string(),
  clusterId: z.string(),
  name: z.string(),
  source: z.string(),
  kind: z.enum(["website", "clarity", "analytics", "inbox", "chat", "payments", "calendar", "crm", "documents", "monitor", "repository"]),
  events: z.array(z.string()),
  subscribers: z.array(z.string()),
  health: z.enum(["ok", "degraded", "down"]),
  scopes: z.array(z.string()),
  retentionDays: z.number().int(),
  personalData: z.boolean(),
  lastEventAt: IsoDate,
  eventsPerHour: z.number(),
});
export type Sensor = z.infer<typeof Sensor>;

export const TrackingPlanItem = z.object({
  id: z.string(),
  selector: z.string(),
  elementLabel: z.string(),
  eventName: z.string(),
  properties: z.array(z.string()),
  privacy: z.object({ personalData: z.boolean(), maskText: z.boolean() }),
  subscribers: z.array(z.string()),
  createdBy: z.string(),
  createdAt: IsoDate,
});
export type TrackingPlanItem = z.infer<typeof TrackingPlanItem>;

export const TemplateField = z.object({
  key: z.string(),
  label: z.string(),
  sensors: z.array(z.string()),
  required: z.boolean(),
  freshnessHours: z.number().int(),
  value: z.string().nullable(),
  filledAt: IsoDate.nullable(),
  filledBy: z.string().nullable(),
  source: z.string().nullable(),
});
export type TemplateField = z.infer<typeof TemplateField>;

export const Template = z.object({
  id: z.string(),
  tenantId: z.string(),
  clusterId: z.string(),
  name: z.string(),
  fields: z.array(TemplateField),
  cadence: z.string(),
  owner: z.string(),
  assignedAgents: z.array(z.string()),
  freshnessRule: z.string(),
  requiredEvidence: z.array(z.string()),
  status: z.enum(["complete", "partial", "stale"]),
});
export type Template = z.infer<typeof Template>;

export const ResolverRule = z.object({
  id: z.string(),
  tenantId: z.string(),
  event: z.string(),
  match: z.string(),
  skill: VersionRef,
  agentId: z.string(),
  priority: z.number().int(),
  triggerEval: z.object({ cases: z.number().int(), passRate: z.number(), lastRunAt: IsoDate }),
});
export type ResolverRule = z.infer<typeof ResolverRule>;

export const GraphNode = z.object({
  id: z.string(),
  type: NodeType,
  label: z.string(),
  refId: z.string(),
  clusterId: z.string(),
  sensitivity: Sensitivity,
  requires: z.object({ capability: z.string().nullable(), roles: z.array(z.string()) }),
  x: z.number(),
  y: z.number(),
});
export type GraphNode = z.infer<typeof GraphNode>;

export const GraphEdge = z.object({
  id: z.string(),
  source: z.string(),
  target: z.string(),
  kind: z.enum(["uses", "governs", "feeds", "fills", "depends", "grants", "evidences"]),
  requiresCapability: z.string().nullable(),
});
export type GraphEdge = z.infer<typeof GraphEdge>;

export const Graph = z.object({ nodes: z.array(GraphNode), edges: z.array(GraphEdge) });
export type Graph = z.infer<typeof Graph>;

export const LibrarianItem = z.object({
  id: z.string(),
  kind: z.enum(["conflict", "stale", "duplicate", "orphan", "unverified"]),
  title: z.string(),
  detail: z.string(),
  factIds: z.array(z.string()),
  policyId: z.string().nullable(),
  documentId: z.string().nullable(),
  proposal: z
    .object({
      winningSource: z.string(),
      newValidFrom: IsoDate,
      dependents: z.array(z.object({ type: z.string(), id: z.string(), label: z.string() })),
    })
    .nullable(),
  status: z.enum(["open", "proposed", "resolved"]),
  changeRequestId: z.string().nullable(),
  createdAt: IsoDate,
});
export type LibrarianItem = z.infer<typeof LibrarianItem>;
