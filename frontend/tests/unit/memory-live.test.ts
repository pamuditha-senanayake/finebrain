// The HQ API's real answers for every Living memory path (recorded by backend/scripts/memory_contract_fixture.py) parse
// against the page's own zod contracts, so the backend's shapes and the page's never drift apart.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { z } from "zod";
import * as C from "@/contracts";

const ANSWERS = JSON.parse(readFileSync(resolve(__dirname, "../../../backend/samples/memory_live_answers.json"), "utf8")) as Record<string, unknown>;

const SHAPES: [string, z.ZodTypeAny][] = [
  ["memory", C.MemoryMap],
  ["memory/areas/customer_care", C.AreaDetail],
  ["memory/traces", C.TracePage],
  ["memory/traces?flag=surprise", C.TracePage],
  ["memory/traces?flag=drift", C.TracePage],
  ["memory/drifts", z.array(C.DriftItem)],
  ["memory/skills", z.array(C.ExtractedSkill)],
];

describe("the live HQ answers match the Living memory contracts", () => {
  for (const [path, schema] of SHAPES) {
    it(path, () => {
      const result = schema.safeParse(ANSWERS[path]);
      if (!result.success) throw new Error(JSON.stringify(result.error.issues.slice(0, 3)));
    });
  }

  it("one trace, start to end", () => {
    const path = Object.keys(ANSWERS).find((p) => /^memory\/traces\/tr-/.test(p));
    expect(path).toBeTruthy();
    const result = C.TraceDetail.safeParse(ANSWERS[path!]);
    if (!result.success) throw new Error(JSON.stringify(result.error.issues.slice(0, 3)));
  });

  it("every list the page reads has something in it", () => {
    expect((ANSWERS["memory/drifts"] as unknown[]).length).toBeGreaterThan(0);
    expect((ANSWERS["memory/skills"] as unknown[]).length).toBeGreaterThan(0);
    expect((ANSWERS["memory/traces"] as { items: unknown[] }).items.length).toBeGreaterThan(0);
  });
});
