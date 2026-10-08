import { z } from "zod";
import { IsoDate } from "./common";

export const EvidenceItem = z.object({
  key: z.string(),
  label: z.string(),
  satisfiedBy: z.string().nullable(),
});
export type EvidenceItem = z.infer<typeof EvidenceItem>;

export const Obligation = z.object({
  id: z.string(),
  tenantId: z.string(),
  clusterId: z.string(),
  title: z.string(),
  jurisdiction: z.string(),
  category: z.enum(["tax", "statutory", "contract", "renewal"]),
  dueAt: IsoDate,
  prepareBy: IsoDate,
  requiredEvidence: z.array(EvidenceItem),
  readiness: z.number(),
  status: z.enum(["green", "amber", "red"]),
  dri: z.string(),
  isSample: z.boolean(),
  note: z.string(),
});
export type Obligation = z.infer<typeof Obligation>;

export const GrantRequest = z.object({
  source: z.string(),
  scope: z.string(),
  retentionDays: z.number().int(),
  agents: z.array(z.string()),
  revoke: z.string(),
});
export type GrantRequest = z.infer<typeof GrantRequest>;

export const EvidenceRequest = z.object({
  id: z.string(),
  tenantId: z.string(),
  obligationId: z.string(),
  evidenceKey: z.string(),
  item: z.string(),
  requestedFrom: z.string(),
  status: z.enum(["open", "fulfilled", "awaiting_grant_approval", "expired"]),
  dueAt: IsoDate,
  createdAt: IsoDate,
  escalationLevel: z.number().int(),
  suggestedGrant: GrantRequest.nullable(),
  fulfilledBy: z.object({ kind: z.enum(["upload", "grant"]), ref: z.string() }).nullable(),
});
export type EvidenceRequest = z.infer<typeof EvidenceRequest>;

export const Grant = z.object({
  id: z.string(),
  tenantId: z.string(),
  source: z.string(),
  scope: z.string(),
  retentionDays: z.number().int(),
  agents: z.array(z.string()),
  revoke: z.string(),
  status: z.enum(["pending", "active", "revoked"]),
  requestedBy: z.string(),
  approvalId: z.string().nullable(),
  createdAt: IsoDate,
});
export type Grant = z.infer<typeof Grant>;

export const Risk = z.object({
  id: z.string(),
  title: z.string(),
  likelihood: z.enum(["low", "medium", "high"]),
  impact: z.enum(["low", "medium", "high"]),
  owner: z.string(),
  mitigation: z.string(),
  linkedObligation: z.string().nullable(),
});
export type Risk = z.infer<typeof Risk>;

export const ReadinessGap = z.object({
  id: z.string(),
  target: z.object({ kind: z.enum(["obligation", "template", "loop"]), id: z.string(), label: z.string() }),
  missing: z.string(),
  dueAt: IsoDate,
  action: z.enum(["dispatch_agent", "request_dri", "request_grant"]),
  dri: z.string(),
  escalationDays: z.array(z.number().int()),
  requestId: z.string().nullable(),
});
export type ReadinessGap = z.infer<typeof ReadinessGap>;

export const ReadinessRule = z.object({
  id: z.string(),
  target: z.string(),
  requires: z.string(),
  checkEvery: z.string(),
  escalationDays: z.array(z.number().int()),
  lastRunAt: IsoDate,
});
export type ReadinessRule = z.infer<typeof ReadinessRule>;
