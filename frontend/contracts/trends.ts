import { z } from "zod";
import { IsoDate } from "./common";

// One unusual week found by the weekly spike check (S13). The screen shows one card at a time.
export const TrendCard = z.object({
  id: z.string(),
  tenantId: z.string(),
  metric: z.string(),
  segment: z.string(),
  ownerId: z.string(),
  weeks: z.array(z.number().int()).length(12),
  usual: z.number(),
  latest: z.number().int(),
  ratio: z.number(),
  status: z.enum(["new", "known"]),
  caseIds: z.array(z.string()),
  foundAt: IsoDate,
});
export type TrendCard = z.infer<typeof TrendCard>;
