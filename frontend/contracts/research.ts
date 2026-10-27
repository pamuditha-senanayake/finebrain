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

// --- Research Lab (backend/app/research): packs, preregistrations, experiments, results and cases

export const LabAudit = z.object({ key: z.string(), label: z.string(), status: z.enum(["pass", "warn", "fail", "not_applicable"]), detail: z.string(), lines: z.array(z.string()) });
export type LabAudit = z.infer<typeof LabAudit>;

export const LabPack = z.object({
  id: z.string(),
  kind: z.string(),
  name: z.string(),
  version: z.string(),
  sha256: z.string(),
  uploadedBy: z.string(),
  uploadedAt: z.string().optional(),
  audit: z.object({ verdict: z.enum(["pass", "warn", "fail"]), checks: z.array(LabAudit), reasons: z.record(z.string(), z.string()).default({}) }),
});
export type LabPack = z.infer<typeof LabPack>;

export const LabHypothesis = z.object({
  id: z.string(),
  metric: z.string(),
  comparator: z.enum(["at_least", "at_most", "below", "above"]),
  threshold: z.number(),
  conditions: z.array(z.string()),
  test: z.enum(["exact_mcnemar", "paired_bootstrap", "wilson", "rule_of_three", "bootstrap_mean"]),
  alpha: z.number().default(0.05),
  diagnosisStage: z.number().int().optional(),
});
export type LabHypothesis = z.infer<typeof LabHypothesis>;

export const LabPrereg = z.object({
  id: z.string(),
  paper: ResearchPaper,
  title: z.string(),
  hypotheses: z.array(LabHypothesis),
  sha256: z.string(),
  lockedAt: z.string().optional(),
  lockedBy: z.string().optional(),
});
export type LabPrereg = z.infer<typeof LabPrereg>;

export const LabExperiment = z.object({
  id: z.string(),
  paper: ResearchPaper,
  packId: z.string().optional(),
  preregId: z.string().optional(),
  conditions: z.array(z.string()),
  seeds: z.array(z.number()),
  trials: z.number(),
  models: z.record(z.string(), z.string()),
  budgetUsd: z.number(),
  configSha256: z.string(),
  gitCommit: z.string(),
  status: z.enum(["draft", "estimated", "running", "paused", "budget_reached", "finished", "failed", "invalid_run"]),
  startedAt: z.string().optional(),
  finishedAt: z.string().optional(),
  costUsd: z.number().optional(),
  notes: z.record(z.string(), z.unknown()).default({}),
});
export type LabExperiment = z.infer<typeof LabExperiment>;

export const LabProgress = z.object({ status: LabExperiment.shape.status, stalled: z.boolean().default(false), done: z.number(), total: z.number(), costUsd: z.number(), budgetUsd: z.number(), error: z.string().nullable().optional() });
export type LabProgress = z.infer<typeof LabProgress>;

export const LabResults = z.object({
  experiment: LabExperiment,
  metrics: z.array(ResearchMetric),
  verdicts: z.array(ResearchVerdict),
  hypotheses: z.array(LabHypothesis),
  preregSha256: z.string().nullable(),
  conditions: z.record(z.string(), z.string()),
});
export type LabResults = z.infer<typeof LabResults>;

export const LabCase = z.object({
  condition: z.string(),
  seed: z.number(),
  trial: z.number(),
  caseId: z.string(),
  passed: z.boolean().optional(),
  costUsd: z.number().optional(),
  latencyMs: z.number().optional(),
  outcome: z.object({ kind: z.string(), question: z.string().optional(), label: z.string(), answer: z.string(), expected: z.string(), superseded: z.array(z.string()), items: z.array(z.string()), eitherHit: z.boolean().optional(), either_hit: z.boolean().optional(), as_of: z.string().optional() }),
});
export type LabCase = z.infer<typeof LabCase>;

export const LabCasePage = z.object({ total: z.number(), offset: z.number(), items: z.array(LabCase) });
export type LabCasePage = z.infer<typeof LabCasePage>;

export const LabOptions = z.object({
  conditions: z.array(z.object({ code: z.string(), label: z.string(), available: z.boolean(), reason: z.string().optional() })),
  models: z.array(z.object({ id: z.string(), inUsdPerMillion: z.number(), outUsdPerMillion: z.number() })),
  maxBudgetUsd: z.number(),
});
export type LabOptions = z.infer<typeof LabOptions>;
