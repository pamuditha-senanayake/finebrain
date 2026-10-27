// Research Lab step 1: every research number carries its provenance, and a sample value can never pass as a result.
import { describe, expect, it } from "vitest";
import { ResearchSnapshot } from "@/contracts/research";
import { parseExperimentOutput, toCsv } from "@/features/research/import-adapter";

const metric = { key: "stale", label: "Stale answers", definition: "d", value: 0.1, unit: "ratio", condition: "C3", series: [] };
const snapshot = { paper: "policies", title: "Freshness", isSample: true, source: "", takenAt: "2026-10-27T00:00:00.000Z", metrics: [metric] };

describe("research provenance", () => {
  it("loads an old snapshot as sample, with no verdicts", () => {
    const parsed = ResearchSnapshot.parse(snapshot);
    expect(parsed.metrics[0].provenance).toBe("sample");
    expect(parsed.verdicts).toEqual([]);
  });

  it("reads an imported result without provenance as lab, and keeps a marked sample as sample", () => {
    const file = [{ ...snapshot, metrics: [metric, { ...metric, key: "mock", provenance: "sample" }] }];
    const result = parseExperimentOutput(file);
    if (!result.ok) throw new Error(result.error);
    expect(result.snapshots[0].isSample).toBe(false);
    expect(result.snapshots[0].metrics.map((m) => m.provenance)).toEqual(["lab", "sample"]);
    expect(toCsv(result.snapshots)).toContain('"lab"');
  });

  it("refuses an unknown provenance", () => {
    const result = parseExperimentOutput([{ ...snapshot, metrics: [{ ...metric, provenance: "guess" }] }]);
    expect(result.ok).toBe(false);
  });
});
