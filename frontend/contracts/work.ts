import { z } from "zod";
import { Criticality, Env, IsoDate, VersionRef } from "./common";

export const RunStatus = z.enum(["running", "succeeded", "escalated", "failed", "blocked", "awaiting_approval"]);
export type RunStatus = z.infer<typeof RunStatus>;

export const TraceStep = z.object({
  id: z.string(),
  idx: z.number().int(),
  kind: z.enum(["judgment", "tool", "retrieval", "access_check", "quality_gate", "human"]),
  title: z.string(),
  decision: z.string(),
  reason: z.string(),
  durationMs: z.number().int(),
  at: IsoDate,
  facts: z.array(z.object({ id: z.string(), statement: z.string(), validFrom: IsoDate, validTo: IsoDate.nullable() })),
  access: z.object({ action: z.string(), decision: z.enum(["allow", "deny"]), ruleId: z.string() }).nullable(),
  gate: z.object({ name: z.string(), passed: z.boolean() }).nullable(),
  tool: z.string().nullable(),
  templateFields: z.array(z.object({ template: z.string(), field: z.string(), value: z.string() })),
  costTokens: z.number().int(),
});
export type TraceStep = z.infer<typeof TraceStep>;

export const Escalation = z.object({
  reason: z.string(),
  risk: z.enum(["low", "medium", "high"]),
  since: IsoDate,
  assignee: z.string().nullable(),
  criticality: Criticality,
});
export type Escalation = z.infer<typeof Escalation>;

export const Run = z.object({
  id: z.string(),
  tenantId: z.string(),
  clusterId: z.string(),
  agentId: z.string(),
  skill: VersionRef,
  env: Env,
  subject: z.string(),
  status: RunStatus,
  startedAt: IsoDate,
  endedAt: IsoDate.nullable(),
  escalation: Escalation.nullable(),
  conversationId: z.string().nullable(),
  costTokens: z.number().int(),
  costUsd: z.number(),
  latencyMs: z.number().int(),
  humanTouch: z.boolean(),
  failureClass: z.string().nullable(),
});
export type Run = z.infer<typeof Run>;

export const RunDetail = Run.extend({ steps: z.array(TraceStep) });
export type RunDetail = z.infer<typeof RunDetail>;

export const Message = z.object({
  id: z.string(),
  from: z.enum(["customer", "agent", "human", "system"]),
  author: z.string(),
  text: z.string(),
  at: IsoDate,
  citations: z.array(z.object({ id: z.string(), label: z.string(), validFrom: IsoDate })),
});
export type Message = z.infer<typeof Message>;

export const ProposedAction = z.object({
  id: z.string(),
  label: z.string(),
  tool: z.string(),
  criticality: Criticality,
  status: z.enum(["proposed", "executed", "blocked", "withdrawn"]),
  reason: z.string(),
});
export type ProposedAction = z.infer<typeof ProposedAction>;

export const Conversation = z.object({
  id: z.string(),
  tenantId: z.string(),
  runId: z.string(),
  agentId: z.string(),
  customer: z.string(),
  channel: z.enum(["chat", "email"]),
  topic: z.string(),
  status: z.enum(["agent", "human", "closed"]),
  takenOverBy: z.string().nullable(),
  reasoningSummary: z.string(),
  proposedActions: z.array(ProposedAction),
  messages: z.array(Message),
  skillifiedTo: z.string().nullable(),
  updatedAt: IsoDate,
});
export type Conversation = z.infer<typeof Conversation>;

export const AccessDecision = z.object({
  id: z.string(),
  tenantId: z.string(),
  at: IsoDate,
  principal: z.string(),
  onBehalfOf: z.string().nullable(),
  action: z.string(),
  resource: z.string(),
  decision: z.enum(["allow", "deny"]),
  ruleId: z.string(),
  reason: z.string(),
  latencyMs: z.number(),
  runId: z.string().nullable(),
});
export type AccessDecision = z.infer<typeof AccessDecision>;
