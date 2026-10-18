// Sample spikes for the Trends tab. Each is 11 ordinary weeks and one unusual latest week,
// linked to real runs so "See the cases" opens something. The real version comes from S13.
import type { TrendCard } from "@/contracts";
import { DAY, iso, SEED_NOW, type Rng } from "../prng";
import type { TenantData } from "../types";

type Spec = { metric: string; segment: string; ownerId: string; base: number; latest: number; status?: TrendCard["status"] };

const FINEBASE: Spec[] = [
  { metric: "Refund requests", segment: "Colombo, card payments", ownerId: "h-hcs", base: 14, latest: 46 },
  { metric: "Late invoices", segment: "Enterprise plan", ownerId: "h-fd", base: 6, latest: 21 },
  { metric: "Login complaints", segment: "Mobile app", ownerId: "h-founder", base: 9, latest: 25, status: "known" },
];

function median(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function card(d: TenantData, rng: Rng, spec: Spec, index: number): TrendCard {
  const weeks = Array.from({ length: 11 }, () => Math.max(1, spec.base + rng.int(-3, 3)));
  weeks.push(spec.latest);
  const usual = median(weeks.slice(0, 11));
  const caseIds = d.runs.slice(index * 5, index * 5 + 5).map((r) => r.id);
  return {
    id: `tr-${index}`, tenantId: d.tenant.id, metric: spec.metric, segment: spec.segment, ownerId: spec.ownerId,
    weeks, usual, latest: spec.latest, ratio: Math.round((spec.latest / usual) * 10) / 10,
    status: spec.status ?? "new", caseIds, foundAt: iso(SEED_NOW - index * DAY),
  };
}

export function seedTrends(d: TenantData, rng: Rng, ownerId?: string) {
  const specs = ownerId ? FINEBASE.map((s) => ({ ...s, ownerId })) : FINEBASE;
  d.trends = specs.map((spec, i) => card(d, rng, spec, i));
}
