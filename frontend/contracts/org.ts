import { z } from "zod";
import { Criticality, IsoDate, Tier, VersionRef } from "./common";

export const CriticalityThresholds = z.object({
  refundAutoLimitMinor: z.number().int(),
  writeOffLimitMinor: z.number().int(),
  goodwillCreditLimitMinor: z.number().int(),
  l2ApprovalCeiling: Criticality,
  coolingPeriodHoursC4: z.number().int(),
  approvalExpiryHours: z.number().int(),
});
export type CriticalityThresholds = z.infer<typeof CriticalityThresholds>;

export const Tenant = z.object({
  id: z.string(),
  name: z.string(),
  currency: z.string(),
  timezone: z.string(),
  locale: z.string(),
  brand: z.object({ primary: z.string(), mark: z.string() }),
  clusters: z.array(z.string()),
  criticalityThresholds: CriticalityThresholds,
  isScaleDemo: z.boolean(),
});
export type Tenant = z.infer<typeof Tenant>;

export const Cluster = z.object({
  id: z.string(),
  tenantId: z.string(),
  name: z.string(),
  description: z.string(),
  status: z.enum(["active", "planned"]),
  connectors: z.array(z.string()),
  dri: z.string().nullable(),
  health: z.number(),
  autonomyRate: z.number(),
  escalationRate: z.number(),
  moneyAtStakeMinor: z.number().int(),
  openRisks: z.number().int(),
  costPerTaskUsd: z.number(),
});
export type Cluster = z.infer<typeof Cluster>;

export const Human = z.object({
  id: z.string(),
  tenantId: z.string(),
  name: z.string(),
  title: z.string(),
  tier: Tier,
  roles: z.array(z.string()),
  attributes: z.record(z.string(), z.string()),
  driOf: z.array(z.string()),
  maxApprovalCriticality: Criticality,
  color: z.string(),
});
export type Human = z.infer<typeof Human>;

export const Autonomy = z.enum(["trainee", "supervised", "autonomous"]);
export type Autonomy = z.infer<typeof Autonomy>;

export const AgentStatus = z.enum(["idle", "working", "blocked", "error", "paused"]);
export type AgentStatus = z.infer<typeof AgentStatus>;

export const WorkKind = z.enum(["retrieval", "judgment", "tool"]);
export type WorkKind = z.infer<typeof WorkKind>;

export const Agent = z.object({
  id: z.string(),
  tenantId: z.string(),
  name: z.string(),
  kind: z.enum(["worker", "supervisor"]),
  tier: Tier,
  clusterId: z.string(),
  description: z.string(),
  autonomy: Autonomy,
  skills: z.array(VersionRef),
  capabilities: z.array(z.string()),
  accessLevel: z.enum(["public", "internal", "confidential", "restricted"]),
  sensors: z.array(z.string()),
  templates: z.array(z.string()),
  policies: z.array(z.string()),
  status: AgentStatus,
  workKind: WorkKind.nullable(),
  dri: z.string(),
  queueDepth: z.number().int(),
  throughputPerHour: z.number(),
  errorRate: z.number(),
  costTodayUsd: z.number(),
  taskSuccess: z.number(),
  training: z.array(z.object({ at: IsoDate, event: z.string(), by: z.string() })),
});
export type Agent = z.infer<typeof Agent>;
