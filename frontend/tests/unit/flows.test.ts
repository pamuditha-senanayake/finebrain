// The seven product flows, exercised against the domain operations the mock API runs.
import { describe, expect, it } from "vitest";
import { OPS, type Ctx } from "@/lib/mock/ops";
import { HOUR, SEED_NOW } from "@/lib/mock/prng";
import { buildFinebase } from "@/lib/mock/seed/build";
import type { TenantData } from "@/lib/mock/types";

function as(d: TenantData, id: string, now = SEED_NOW): Ctx {
  const h = d.humans.find((x) => x.id === id)!;
  return { now, actor: { kind: "human", id: h.id, name: h.name } };
}

describe("flow 1: refund outside policy", () => {
  it("escalates, gets skillified, tested, approved at C3 by the L1 DRI, merged and audited", () => {
    const d = buildFinebase();
    expect(d.runs.find((r) => r.id === "run-1042")?.status).toBe("escalated");
    OPS.takeover(d, as(d, "h-op"), { conversationId: "conv-1042" });
    OPS.sendMessage(d, as(d, "h-op"), { conversationId: "conv-1042", text: "I'll ask our head of customer success to approve a prorated refund." });
    const cr = OPS.skillify(d, as(d, "h-op"), { conversationId: "conv-1042" });
    expect(cr.status).toBe("draft");
    expect(cr.criticality).toBe(3);
    OPS.runChecks(d, as(d, "h-aiops"), { changeRequestId: cr.id });
    expect(cr.status).toBe("awaiting_approval");
    expect(cr.impactPreview?.summary).toMatch(/37 of the last 412/);
    const ap = d.approvals.find((a) => a.id === cr.approvalId)!;
    expect(() => OPS.decide(d, as(d, "h-aiops"), { approvalId: ap.id, decision: "approve" })).toThrow(/C3/);
    OPS.decide(d, as(d, "h-hcs"), { approvalId: ap.id, decision: "approve" });
    expect(cr.status).toBe("merged");
    const skill = d.skills.find((s) => s.id === "refund-late-annual")!;
    expect(skill.branch).toBe("main");
    expect(skill.status).toBe("active");
    const trail = d.audit.filter((a) => a.correlationId === "conv:conv-1042").map((a) => a.action);
    expect(trail).toEqual(expect.arrayContaining(["conversation.taken_over", "conversation.skillified", "change_request.opened", "change_request.tested", "approval.approved", "change_request.merged"]));
  });
});

describe("flow 2: tax readiness", () => {
  it("finds missing proof 21 days ahead, requests it, and turns green after upload", () => {
    const d = buildFinebase();
    const vat = d.obligations.find((o) => o.id === "ob-vat-sep")!;
    expect(vat.status).not.toBe("green");
    OPS.runReadinessScheduler(d, as(d, "h-ks"));
    const reqs = d.evidenceRequests.filter((r) => r.obligationId === "ob-vat-sep");
    expect(reqs.length).toBe(2);
    for (const r of reqs) OPS.uploadEvidence(d, as(d, "h-fd"), { requestId: r.id, fileName: `${r.evidenceKey}.pdf`, sizeKb: 120 });
    expect(vat.readiness).toBe(100);
    expect(vat.status).toBe("green");
    const fact = d.facts.find((f) => f.id === vat.requiredEvidence[1].satisfiedBy)!;
    expect(fact.evidence[0].documentId).toBeTruthy();
  });

  it("can satisfy the gap through a scoped finance inbox grant that needs two L1 approvals", () => {
    const d = buildFinebase();
    OPS.runReadinessScheduler(d, as(d, "h-ks"));
    const req = d.evidenceRequests.find((r) => r.suggestedGrant)!;
    const { approval } = OPS.requestGrant(d, as(d, "h-fd"), { requestId: req.id });
    expect(approval.criticality).toBe(4);
    OPS.decide(d, as(d, "h-fd"), { approvalId: approval.id, decision: "approve" });
    expect(approval.status).toBe("pending");
    OPS.decide(d, as(d, "h-founder"), { approvalId: approval.id, decision: "approve" });
    expect(approval.status).toBe("approved");
    expect(req.status).toBe("fulfilled");
    expect(d.agents.find((a) => a.id === "a-compliance")!.capabilities).toContain("finance:read");
  });
});

describe("flow 3: policy drift", () => {
  it("proposes invalidation with a new validity interval and updates all dependents in one change request", () => {
    const d = buildFinebase();
    const cr = OPS.librarianPropose(d, as(d, "h-ks"), { itemId: "lib-refund-window" });
    expect(cr.criticality).toBe(3);
    expect(cr.changes.filter((c) => c.field === "references").length).toBeGreaterThanOrEqual(3);
    OPS.runChecks(d, as(d, "h-ks"), { changeRequestId: cr.id });
    OPS.decide(d, as(d, "h-hcs"), { approvalId: cr.approvalId!, decision: "approve" });
    const versions = d.policies.filter((p) => p.key === "refund-window").sort((a, b) => a.version - b.version);
    expect(versions.at(-1)!.version).toBe(4);
    expect(versions.at(-2)!.validTo).toBe("2026-11-01T00:00:00Z");
    expect(versions.at(-2)!.supersededBy).toBe(versions.at(-1)!.id);
  });
});

describe("flow 4: website loop", () => {
  it("previews on a sandbox branch, runs an A/B test and records the learning", () => {
    const d = buildFinebase();
    OPS.experimentPreview(d, as(d, "h-aiops"), { experimentId: "exp-pricing-toggle" });
    OPS.experimentStart(d, as(d, "h-aiops"), { experimentId: "exp-pricing-toggle" });
    const exp = OPS.experimentConclude(d, as(d, "h-aiops"), { experimentId: "exp-pricing-toggle" });
    expect(exp.impact).not.toBeNull();
    const { changeRequest } = OPS.experimentKeep(d, as(d, "h-aiops"), { experimentId: "exp-pricing-toggle" });
    expect(changeRequest.criticality).toBe(3);
    expect(exp.learning).toBeTruthy();
  });
});

describe("flow 5: blocked action", () => {
  it("logs the denial and needs two L1 approvals for the proposed grant", () => {
    const d = buildFinebase();
    expect(d.accessDecisions.find((a) => a.id === "ad-2203")?.decision).toBe("deny");
    const ap = d.approvals.find((a) => a.id === "apr-sentinel-grant")!;
    OPS.decide(d, as(d, "h-hcs"), { approvalId: ap.id, decision: "approve" });
    expect(ap.status).toBe("pending");
    expect(() => OPS.decide(d, as(d, "h-hcs"), { approvalId: ap.id, decision: "approve" })).toThrow(/two person/);
    OPS.decide(d, as(d, "h-founder"), { approvalId: ap.id, decision: "approve" });
    expect(ap.status).toBe("approved");
    expect(d.agents.find((a) => a.id === "a-care")!.capabilities).toContain("refund:issue");
  });
});

describe("flow 6: overnight improvement", () => {
  it("applies C0 and C1 fixes and drafts the rest", () => {
    const d = buildFinebase();
    const digest = OPS.runOvernightReview(d, as(d, "h-aiops", SEED_NOW + HOUR));
    expect(digest.items.some((i) => i.kind === "auto_fix" && i.criticality === 0)).toBe(true);
    expect(digest.items.some((i) => i.kind === "auto_fix" && i.criticality === 1)).toBe(true);
    expect(digest.items.some((i) => i.kind === "drafted" && i.criticality >= 2)).toBe(true);
  });
});
