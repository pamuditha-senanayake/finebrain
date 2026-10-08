import { z } from "zod";
import { IsoDate } from "./common";

export const LoopStage = z.object({
  key: z.enum(["sensor", "policy", "tool", "gate", "learning"]),
  label: z.string(),
  refs: z.array(z.string()),
  metric: z.object({ label: z.string(), value: z.string(), trend: z.number() }),
  pending: z.number().int(),
});
export type LoopStage = z.infer<typeof LoopStage>;

export const Experiment = z.object({
  id: z.string(),
  loopId: z.string(),
  title: z.string(),
  hypothesis: z.string(),
  signal: z.string(),
  proposedBy: z.string(),
  branch: z.string().nullable(),
  variants: z.array(z.object({ id: z.string(), name: z.string(), traffic: z.number(), conversion: z.number().nullable() })),
  status: z.enum(["proposed", "previewed", "running", "concluded", "kept", "discarded"]),
  impact: z.enum(["positive", "negative", "neutral"]).nullable(),
  learning: z.string().nullable(),
  changeRequestId: z.string().nullable(),
  criticality: z.number().int(),
  startedAt: IsoDate.nullable(),
  endedAt: IsoDate.nullable(),
});
export type Experiment = z.infer<typeof Experiment>;

export const Loop = z.object({
  id: z.string(),
  tenantId: z.string(),
  clusterId: z.string(),
  name: z.string(),
  description: z.string(),
  stages: z.array(LoopStage),
  runs7d: z.number().int(),
  successRate: z.number(),
  autonomyRate: z.number(),
  history: z.array(z.object({ day: z.string(), runs: z.number().int(), success: z.number() })),
  experiments: z.array(z.string()),
  dri: z.string(),
});
export type Loop = z.infer<typeof Loop>;
