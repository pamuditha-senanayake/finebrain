import { z } from "zod";
import { Actor, Criticality, Env, IsoDate, Tier } from "./common";

export const Change = z.object({
  op: z.enum(["add", "modify", "remove"]),
  nodeType: z.string(),
  nodeId: z.string(),
  label: z.string(),
  field: z.string().nullable(),
  before: z.string().nullable(),
  after: z.string().nullable(),
});
export type Change = z.infer<typeof Change>;

export const Commit = z.object({
  id: z.string(),
  tenantId: z.string(),
  branch: z.string(),
  parentId: z.string().nullable(),
  author: Actor,
  message: z.string(),
  changes: z.array(Change),
  criticality: Criticality,
  evidence: z.array(z.string()),
  createdAt: IsoDate,
  tag: z.string().nullable(),
});
export type Commit = z.infer<typeof Commit>;

export const Branch = z.object({
  id: z.string(),
  tenantId: z.string(),
  name: z.string(),
  env: Env,
  base: z.string().nullable(),
  head: z.string().nullable(),
  status: z.enum(["open", "merged", "abandoned", "protected"]),
  description: z.string(),
  createdBy: Actor,
  createdAt: IsoDate,
});
export type Branch = z.infer<typeof Branch>;

export const ImpactPreview = z.object({
  runsReplayed: z.number().int(),
  decisionsChanged: z.number().int(),
  predictedRisk: z.enum(["low", "medium", "high"]),
  summary: z.string(),
  examples: z.array(z.object({ runId: z.string(), before: z.string(), after: z.string() })),
});
export type ImpactPreview = z.infer<typeof ImpactPreview>;

export const TestResult = z.object({
  suite: z.string(),
  total: z.number().int(),
  passed: z.number().int(),
  failed: z.number().int(),
  passK: z.number(),
  k: z.number().int(),
  ranAt: IsoDate,
});
export type TestResult = z.infer<typeof TestResult>;

export const ChangeRequestKind = z.enum(["skill", "policy", "fact", "grant", "website", "fix", "security", "template"]);

export const ChangeRequest = z.object({
  id: z.string(),
  tenantId: z.string(),
  title: z.string(),
  kind: ChangeRequestKind,
  fromBranch: z.string(),
  toBranch: z.string(),
  commits: z.array(z.string()),
  plainDiff: z.array(z.string()),
  changes: z.array(Change),
  impactPreview: ImpactPreview.nullable(),
  tests: TestResult.nullable(),
  approvalId: z.string().nullable(),
  status: z.enum(["draft", "testing", "awaiting_approval", "approved", "merged", "rejected", "expired", "changes_requested", "conflict"]),
  criticality: Criticality,
  criticalityReasons: z.array(z.string()),
  drafter: Actor,
  dri: z.string(),
  clusters: z.array(z.string()),
  createdAt: IsoDate,
  mergedAt: IsoDate.nullable(),
  coolingUntil: IsoDate.nullable(),
  correlationId: z.string(),
});
export type ChangeRequest = z.infer<typeof ChangeRequest>;

export const ApprovalVote = z.object({
  by: z.string(),
  at: IsoDate,
  decision: z.enum(["approve", "reject", "request_changes", "delegate"]),
  comment: z.string(),
});
export type ApprovalVote = z.infer<typeof ApprovalVote>;

export const Approval = z.object({
  id: z.string(),
  tenantId: z.string(),
  subject: z.object({ kind: z.enum(["change_request", "action", "grant"]), id: z.string() }),
  title: z.string(),
  summary: z.string(),
  criticality: Criticality,
  requiredApprovers: z.object({ tier: Tier, count: z.number().int(), roles: z.array(z.string()) }),
  votes: z.array(ApprovalVote),
  dueAt: IsoDate,
  createdAt: IsoDate,
  status: z.enum(["pending", "approved", "rejected", "changes_requested", "expired"]),
  delegatedTo: z.string().nullable(),
  dri: z.string(),
  drafter: Actor,
  evidence: z.array(z.string()),
  correlationId: z.string(),
});
export type Approval = z.infer<typeof Approval>;

export const Decision = z.object({
  decision: z.enum(["approve", "reject", "request_changes", "delegate"]),
  comment: z.string().default(""),
  delegateTo: z.string().nullable().default(null),
});
export type Decision = z.infer<typeof Decision>;
