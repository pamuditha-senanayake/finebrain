import { z } from "zod";
import { IsoDate } from "./common";

export const ResearchMetric = z.object({
  key: z.string(),
  label: z.string(),
  definition: z.string(),
  value: z.number(),
  unit: z.enum(["ratio", "percent", "ms", "count"]),
  condition: z.string(),
  series: z.array(z.object({ x: z.string(), y: z.number() })),
});
export type ResearchMetric = z.infer<typeof ResearchMetric>;

export const ResearchPaper = z.enum(["skills", "policies", "security", "integration"]);
export type ResearchPaper = z.infer<typeof ResearchPaper>;

export const ResearchSnapshot = z.object({
  paper: ResearchPaper,
  title: z.string(),
  isSample: z.boolean(),
  source: z.string(),
  takenAt: IsoDate,
  metrics: z.array(ResearchMetric),
});
export type ResearchSnapshot = z.infer<typeof ResearchSnapshot>;
