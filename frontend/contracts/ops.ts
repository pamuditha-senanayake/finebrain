import { z } from "zod";
import { Actor, Criticality, Env, IsoDate } from "./common";

export const AuditEvent = z.object({
  id: z.string(),
  tenantId: z.string(),
  at: IsoDate,
  actor: Actor,
  action: z.string(),
  target: z.object({ type: z.string(), id: z.string(), label: z.string() }),
  env: Env,
  criticality: Criticality,
  detail: z.string(),
  correlationId: z.string().nullable(),
});
export type AuditEvent = z.infer<typeof AuditEvent>;

export const Notification = z.object({
  id: z.string(),
  tenantId: z.string(),
  at: IsoDate,
  to: z.string().nullable(),
  title: z.string(),
  body: z.string(),
  href: z.string(),
  kind: z.enum(["approval", "evidence", "escalation", "digest", "security", "info"]),
  read: z.boolean(),
});
export type Notification = z.infer<typeof Notification>;

export const LegibilityCell = z.object({
  activity: z.string(),
  clusterId: z.string(),
  agent: z.string(),
  sensed: z.boolean(),
  skilled: z.boolean(),
  governed: z.boolean(),
  reported: z.boolean(),
});
export type LegibilityCell = z.infer<typeof LegibilityCell>;

export const ClusterKpi = z.object({
  clusterId: z.string(),
  runs24h: z.number().int(),
  autonomyRate: z.number(),
  escalationRate: z.number(),
  costPerResolvedUsd: z.number(),
  moneyAtStakeMinor: z.number().int(),
  openRisks: z.number().int(),
  health: z.number(),
});
export type ClusterKpi = z.infer<typeof ClusterKpi>;

export const Overview = z.object({
  kpis: z.array(ClusterKpi),
  totals: z.object({
    runs24h: z.number().int(),
    autonomyRate: z.number(),
    escalationRate: z.number(),
    costPerResolvedUsd: z.number(),
    moneyAtStakeMinor: z.number().int(),
    openRisks: z.number().int(),
    pendingApprovals: z.number().int(),
    activeAgents: z.number().int(),
  }),
  legibility: z.array(LegibilityCell),
  trend: z.array(z.object({ day: z.string(), autonomy: z.number(), escalation: z.number(), runs: z.number().int() })),
  /** Runs started per 30 minute slot over the last 24 hours, oldest first. The last slot fills live. */
  runSeries: z.array(z.object({ at: z.string(), runs: z.number().int() })),
  runningNow: z.number().int(),
  costs: z.object({ weekUsd: z.number(), prevWeekUsd: z.number(), monthUsd: z.number(), prevMonthUsd: z.number() }),
  entity: z.object({ red: z.number().int(), amber: z.number().int(), risks: z.number().int(), evidenceOpen: z.number().int() }),
});
export type Overview = z.infer<typeof Overview>;

export const DigestItem = z.object({
  id: z.string(),
  kind: z.enum(["auto_fix", "drafted", "failure", "waiting", "run_summary"]),
  title: z.string(),
  detail: z.string(),
  criticality: Criticality,
  href: z.string().nullable(),
  at: IsoDate,
});
export type DigestItem = z.infer<typeof DigestItem>;

export const Digest = z.object({
  date: z.string(),
  generatedAt: IsoDate,
  generatedBy: z.string(),
  runs: z.number().int(),
  failures: z.number().int(),
  failureClasses: z.array(z.object({ name: z.string(), count: z.number().int() })),
  items: z.array(DigestItem),
});
export type Digest = z.infer<typeof Digest>;

export const Analytics = z.object({
  clusters: z.array(
    z.object({
      clusterId: z.string(),
      name: z.string(),
      series: z.array(z.object({ day: z.string(), runs: z.number().int(), autonomy: z.number(), cost: z.number() })),
    }),
  ),
  loops: z.array(z.object({ id: z.string(), name: z.string(), successRate: z.number(), autonomyRate: z.number(), runs7d: z.number().int() })),
  experiments: z.array(z.object({ id: z.string(), title: z.string(), status: z.string(), impact: z.string().nullable() })),
  templates: z.array(z.object({ id: z.string(), name: z.string(), completion: z.number(), status: z.string() })),
});
export type Analytics = z.infer<typeof Analytics>;

export const AskAnswer = z.object({
  question: z.string(),
  answer: z.string(),
  citations: z.array(
    z.object({ id: z.string(), kind: z.string(), label: z.string(), validFrom: IsoDate, validTo: IsoDate.nullable(), href: z.string() }),
  ),
  withheld: z.number().int(),
  scope: z.enum(["page", "system"]).optional(),
  /** Short how-to steps for the page the person is on. */
  guide: z.array(z.string()).optional(),
  actions: z.array(z.object({ label: z.string(), href: z.string() })).optional(),
  /** Set by the real brain: the conversation this answer belongs to, so the next question can refer back. */
  conversationId: z.string().nullable().optional(),
});
export type AskAnswer = z.infer<typeof AskAnswer>;

export const AskTurn = z.object({ question: z.string(), answer: z.string(), at: IsoDate });
export type AskTurn = z.infer<typeof AskTurn>;

export const SearchHit = z.object({ id: z.string(), kind: z.string(), label: z.string(), href: z.string(), hint: z.string() });
export type SearchHit = z.infer<typeof SearchHit>;
