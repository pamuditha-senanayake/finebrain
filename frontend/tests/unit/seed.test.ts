import { describe, expect, it } from "vitest";
import { z } from "zod";
import * as C from "@/contracts";
import { generateSteps, buildFinebase, buildScale } from "@/lib/mock/seed/build";
import { overview } from "@/lib/mock/queries";
import { SEED_NOW } from "@/lib/mock/prng";

describe("seed generator", () => {
  it("is deterministic: the same seed produces the same data", () => {
    const a = buildFinebase();
    const b = buildFinebase();
    expect(JSON.stringify(a)).toEqual(JSON.stringify(b));
  });

  it("matches every contract", () => {
    const d = buildFinebase();
    const checks: [z.ZodTypeAny, unknown][] = [
      [C.Tenant, d.tenant], [z.array(C.Cluster), d.clusters], [z.array(C.Human), d.humans], [z.array(C.Agent), d.agents],
      [z.array(C.Skill), d.skills], [z.array(C.Policy), d.policies], [z.array(C.Fact), d.facts], [z.array(C.Document), d.documents],
      [z.array(C.Sensor), d.sensors], [z.array(C.Template), d.templates], [C.Graph, d.graph], [z.array(C.Run), d.runs],
      [z.array(C.Conversation), d.conversations], [z.array(C.AccessDecision), d.accessDecisions], [z.array(C.Branch), d.branches],
      [z.array(C.Commit), d.commits], [z.array(C.ChangeRequest), d.changeRequests], [z.array(C.Approval), d.approvals],
      [z.array(C.Obligation), d.obligations], [z.array(C.Loop), d.loops], [z.array(C.Experiment), d.experiments],
      [z.array(C.AuditEvent), d.audit], [C.Digest, d.digest], [C.Overview, overview(d, SEED_NOW)], [z.array(C.LibrarianItem), d.librarian],
    ];
    for (const [schema, value] of checks) {
      const r = schema.safeParse(value);
      if (!r.success) throw new Error(JSON.stringify(r.error.issues.slice(0, 3)));
    }
    for (const run of d.runs.slice(0, 50)) expect(z.array(C.TraceStep).safeParse(generateSteps(run, d)).success).toBe(true);
  });

  it("seeds the Finebase tenant at the size the brief asks for", () => {
    const d = buildFinebase();
    expect(d.tenant.currency).toBe("LKR");
    expect(d.tenant.timezone).toBe("Asia/Colombo");
    expect(d.agents.filter((a) => a.kind === "worker")).toHaveLength(12);
    expect(d.agents.filter((a) => a.kind === "supervisor")).toHaveLength(3);
    expect(d.clusters.filter((c) => c.status === "planned").length).toBeGreaterThanOrEqual(3);
    expect(d.obligations.every((o) => o.isSample)).toBe(true);
  });

  it("seeds a scale tenant with hundreds of agents, tens of thousands of runs and thousands of nodes", () => {
    const d = buildScale();
    expect(d.agents.length).toBeGreaterThanOrEqual(300);
    expect(d.runs.length).toBeGreaterThanOrEqual(10_000);
    expect(d.graph.nodes.length).toBeGreaterThanOrEqual(2_000);
  });
});
