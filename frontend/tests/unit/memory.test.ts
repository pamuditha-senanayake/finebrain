// The living memory mock answers every path in the shape its contract says, and keeps the memory rules
// (Docs/CB_Living_Memory_Architecture.md): patterns inside budget, one area per trace, zero-tolerance security drift.
import { describe, expect, it } from "vitest";
import { z } from "zod";
import * as C from "@/contracts";
import { buildFinebase, buildScale } from "@/lib/mock/seed/build";
import { DRAFT_MIN_SUPPORT, PATTERN_BUDGET } from "@/lib/mock/seed/memory";
import { areaDetail, driftList, memoryMap, skillDraftList, traceDetail, tracePage } from "@/lib/mock/memory-queries";
import { SEED_NOW } from "@/lib/mock/prng";

function expectShape(schema: z.ZodTypeAny, value: unknown) {
  const result = schema.safeParse(value);
  if (!result.success) throw new Error(JSON.stringify(result.error.issues.slice(0, 3)));
}

describe("living memory mock", () => {
  const d = buildFinebase();

  it("answers every path in its contract's shape", () => {
    expectShape(C.MemoryMap, memoryMap(d, SEED_NOW));
    for (const key of C.AreaKey.options) expectShape(C.AreaDetail, areaDetail(d, key, SEED_NOW));
    for (const flag of [null, "surprise", "outside_policy", "drift"]) expectShape(C.TracePage, tracePage(d, null, flag, null));
    expectShape(z.array(C.DriftItem), driftList(d, null, null));
    expectShape(z.array(C.ExtractedSkill), skillDraftList(d));
    const outside = d.memory.traces.filter((t) => t.source === "outside").slice(0, 5);
    for (const t of [...d.memory.traces.slice(0, 40), ...outside]) expectShape(C.TraceDetail, traceDetail(d, t.id));
  });

  it("answers the scale workspace too", () => {
    const scale = buildScale();
    expectShape(C.MemoryMap, memoryMap(scale, SEED_NOW));
    expectShape(C.TracePage, tracePage(scale, null, null, null));
  });

  it("keeps every area inside its pattern budget", () => {
    for (const key of C.AreaKey.options) expect(d.memory.patterns.filter((p) => p.area === key).length).toBeLessThanOrEqual(PATTERN_BUDGET);
  });

  it("puts every trace in one area and one pattern", () => {
    const patternIds = new Set(d.memory.patterns.map((p) => p.id));
    for (const t of d.memory.traces) {
      expect(C.AreaKey.options).toContain(t.area);
      expect(patternIds.has(t.patternId ?? "")).toBe(true);
    }
  });

  it("flags every finished action whose access check said deny", () => {
    const denied = new Set(d.accessDecisions.filter((a) => a.decision === "deny").map((a) => a.runId));
    const finished = d.runs.filter((r) => r.status === "succeeded" && denied.has(r.id));
    const flagged = new Set(driftList(d, null, "security").flatMap((x) => x.evidenceTraceIds));
    for (const run of finished) expect(flagged.has(`tr-${run.id}`)).toBe(true);
  });

  it("shows the refund skill and policy drifting, with evidence", () => {
    const kinds = driftList(d, "customer_care", null).map((x) => x.kind);
    expect(kinds).toEqual(expect.arrayContaining(["skill", "policy"]));
    for (const x of driftList(d, null, null)) expect(x.evidenceTraceIds.length).toBeGreaterThan(0);
  });

  it("drafts skills only from patterns with enough support", () => {
    const drafts = skillDraftList(d);
    expect(drafts.length).toBeGreaterThan(0);
    for (const s of drafts) expect(s.support).toBeGreaterThanOrEqual(DRAFT_MIN_SUPPORT);
  });

  it("pages through every trace with the cursor", () => {
    let cursor: string | null = null;
    let seen = 0;
    do {
      const page = tracePage(d, "customer_care", null, cursor);
      seen += page.items.length;
      cursor = page.nextCursor;
    } while (cursor);
    expect(seen).toBe(tracePage(d, "customer_care", null, null).total);
  });

  it("returns nothing for an unknown area or trace", () => {
    expect(areaDetail(d, "space", SEED_NOW)).toBeNull();
    expect(traceDetail(d, "tr-missing")).toBeNull();
  });
});
