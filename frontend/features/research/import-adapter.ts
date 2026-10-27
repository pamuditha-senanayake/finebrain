import { z } from "zod";
import { Provenance, ResearchMetric, ResearchSnapshot } from "@/contracts/research";

// An imported file may come from before provenance existed, so it is read with provenance optional first.
const ImportedSnapshot = ResearchSnapshot.extend({ metrics: z.array(ResearchMetric.extend({ provenance: Provenance.optional() })) });

/**
 * Import adapter stub for results from the research execution repository.
 * It validates the file against the shared contract. Imported snapshots are real results (isSample false).
 * A metric that names no provenance is an experiment result, so it reads as lab; one marked sample stays sample.
 */
export function parseExperimentOutput(json: unknown): { ok: true; snapshots: ResearchSnapshot[] } | { ok: false; error: string } {
  const parsed = z.array(ImportedSnapshot).safeParse(json);
  if (!parsed.success) return { ok: false, error: parsed.error.issues[0]?.message ?? "Invalid file" };
  return {
    ok: true,
    snapshots: parsed.data.map((s) => ({
      ...s,
      isSample: false,
      source: s.source || "research execution repository",
      metrics: s.metrics.map((m) => ({ ...m, provenance: m.provenance ?? "lab" })),
    })),
  };
}

export function toCsv(snapshots: ResearchSnapshot[]): string {
  const rows = [["paper", "metric", "label", "definition", "value", "unit", "condition", "provenance", "taken_at", "source"]];
  for (const s of snapshots) for (const m of s.metrics) rows.push([s.paper, m.key, m.label, m.definition, String(m.value), m.unit, m.condition, m.provenance, s.takenAt, s.source]);
  return rows.map((r) => r.map((c) => `"${c.replaceAll('"', '""')}"`).join(",")).join("\n");
}
