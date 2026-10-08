import type { EvidenceItem, Obligation } from "@/contracts";

export function readinessOf(items: EvidenceItem[]): number {
  if (items.length === 0) return 100;
  return Math.round((items.filter((i) => i.satisfiedBy).length / items.length) * 100);
}

export function statusOf(readiness: number, dueAt: string, now: number): Obligation["status"] {
  if (readiness === 100) return "green";
  const daysLeft = (new Date(dueAt).getTime() - now) / 86_400_000;
  if (daysLeft <= 7 || readiness < 50) return "red";
  return "amber";
}

export const DEFAULT_ESCALATION_DAYS = [21, 14, 7, 2];

/** How many escalation steps have passed for a request due at dueAt. */
export function escalationLevel(dueAt: string, now: number, steps = DEFAULT_ESCALATION_DAYS): number {
  const daysLeft = (new Date(dueAt).getTime() - now) / 86_400_000;
  return steps.filter((d) => daysLeft <= d).length;
}

export function daysUntil(iso: string, now: number): number {
  return Math.ceil((new Date(iso).getTime() - now) / 86_400_000);
}
