// Trend operations. "Mark as known" quiets a spike so the same week does not alert again.
import { OpError, audit, humanOf, type Ctx } from "./ops";
import type { TenantData } from "./types";

export function markTrendKnown(d: TenantData, ctx: Ctx, { id }: { id: string }) {
  const human = humanOf(d, ctx);
  const trend = d.trends.find((t) => t.id === id);
  if (!trend) throw new OpError("Trend not found", 404);
  trend.status = "known";
  audit(d, ctx, "trend.marked_known", { type: "trend", id, label: trend.metric }, 0, `${human.name} marked ${trend.segment} as known`, null);
  return trend;
}
