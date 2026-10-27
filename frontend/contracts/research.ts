import { z } from "zod";
import { IsoDate } from "./common";

/** Where a number came from. The UI never mixes them silently, and a sample value is never exported as a result. */
export const Provenance = z.enum(["field", "lab", "benchmark", "reference", "sample"]);
export type Provenance = z.infer<typeof Provenance>;
export const EXPORTABLE_PROVENANCE: readonly Provenance[] = ["field", "lab", "benchmark", "reference"];

export const ResearchMetric = z.object({
  key: z.string(),
  label: z.string(),
  definition: z.string(),
  value: z.number(),
  unit: z.enum(["ratio", "percent", "ms", "count", "usd", "tokens"]),
  condition: z.string(),
  series: z.array(z.object({ x: z.union([z.string(), z.number()]), y: z.number() })),
  // A snapshot written before provenance existed was mock data, so it loads as sample.
  provenance: Provenance.default("sample"),
  n: z.number().int().optional(),
  ci: z.object({ low: z.number(), high: z.number(), level: z.number() }).optional(),
  experimentId: z.string().optional(),
});
export type ResearchMetric = z.infer<typeof ResearchMetric>;

export const ResearchVerdict = z.object({
  hypothesisId: z.string(),
  metricKey: z.string(),
  threshold: z.string(),
  observed: z.string(),
  verdict: z.enum(["supported", "not_supported", "invalid_run"]),
  diagnosisStage: z.number().int().optional(),
  test: z.string(),
  pAdjusted: z.number().optional(),
});
export type ResearchVerdict = z.infer<typeof ResearchVerdict>;

export const ResearchPaper = z.enum(["skills", "policies", "security", "integration"]);
export type ResearchPaper = z.infer<typeof ResearchPaper>;

export const ResearchSnapshot = z.object({
  paper: ResearchPaper,
  title: z.string(),
  isSample: z.boolean(),
  source: z.string(),
  takenAt: IsoDate,
  metrics: z.array(ResearchMetric),
  verdicts: z.array(ResearchVerdict).default([]),
  preregId: z.string().optional(),
  preregSha256: z.string().optional(),
});
export type ResearchSnapshot = z.infer<typeof ResearchSnapshot>;
