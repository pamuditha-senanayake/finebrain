import { z } from "zod";
import { ResearchSnapshot } from "@/contracts/research";

/**
 * Import adapter stub for results from the research execution repository.
 * It validates the file against the shared contract. Imported snapshots are real results (isSample false).
 */
export function parseExperimentOutput(json: unknown): { ok: true; snapshots: ResearchSnapshot[] } | { ok: false; error: string } {
  const parsed = z.array(ResearchSnapshot).safeParse(json);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid file" };
  return { ok: true, snapshots: parsed.data.map((s) => ({ ...s, isSample: false, source: s.source || "research execution repository" })) };
}

export function toCsv(snapshots: ResearchSnapshot[]): string {
  const rows = [["paper", "metric", "label", "definition", "value", "unit", "condition", "taken_at", "source"]];
  for (const s of snapshots) for (const m of s.metrics) rows.push([s.paper, m.key, m.label, m.definition, String(m.value), m.unit, m.condition, s.takenAt, s.source]);
  return rows.map((r) => r.map((c) => `"${c.replaceAll('"', '""')}"`).join(",")).join("\n");
}
