import { describe, expect, it } from "vitest";
import { approverFor, assessCriticality, canApprove } from "@/lib/governance/criticality";
import { agentPrincipal, checkNode, humanPrincipal, onBehalfOf } from "@/lib/governance/access";
import { escalationLevel, readinessOf, statusOf } from "@/lib/governance/readiness";
import { buildFinebase } from "@/lib/mock/seed/build";
import { SEED_NOW, DAY } from "@/lib/mock/prng";

const none = { money: false, personalData: false, publicContent: false, legalTax: false, clusters: ["a"] };

describe("criticality engine", () => {
  it("keeps routine work routine", () => {
    expect(assessCriticality("log", none).level).toBe(0);
  });
  it("moves medium work up one level when it touches money", () => {
    expect(assessCriticality("skill_step_edit", { ...none, money: true }).level).toBe(3);
  });
  it("keeps any new skill at C3 even when it handles money", () => {
    expect(assessCriticality("new_skill", { ...none, money: true }).level).toBe(3);
  });
  it("moves C3 to C4 for personal data, legal or tax, or more than one cluster", () => {
    expect(assessCriticality("new_policy", { ...none, personalData: true }).level).toBe(4);
    expect(assessCriticality("new_skill", { ...none, clusters: ["a", "b"] }).level).toBe(4);
  });
  it("never goes above C4", () => {
    expect(assessCriticality("tax_signoff", { ...none, legalTax: true, money: true }).level).toBe(4);
  });
  it("routes approvals by level", () => {
    expect(approverFor(0).automatic).toBe(true);
    expect(approverFor(2)).toMatchObject({ tier: "L2", count: 1 });
    expect(approverFor(3)).toMatchObject({ tier: "L1", count: 1 });
    expect(approverFor(4)).toMatchObject({ tier: "L1", count: 2 });
  });
  it("lets L2 approve only up to C2 and enforces the two person rule", () => {
    const l2 = { id: "s", tier: "L2" as const, maxApprovalCriticality: 2 as const };
    const l1 = { id: "f", tier: "L1" as const, maxApprovalCriticality: 4 as const };
    expect(canApprove(l2, 2, [])).toBeNull();
    expect(canApprove(l2, 3, [])).toMatch(/C3/);
    expect(canApprove(l1, 4, ["f"])).toMatch(/two person/);
  });
});

describe("access", () => {
  const d = buildFinebase();
  const care = agentPrincipal(d.agents.find((a) => a.id === "a-care")!);
  const refundTool = d.graph.nodes.find((n) => n.id === "n:tool:billing.refund")!;
  it("locks the refund tool for the Care Agent with a reason", () => {
    const r = checkNode(care, refundTool);
    expect(r.allowed).toBe(false);
    expect(r.reason).toMatch(/requires/);
  });
  it("never lets an agent exceed the human it acts for", () => {
    const sentinel = agentPrincipal(d.agents.find((a) => a.id === "a-sentinel")!);
    const operator = humanPrincipal(d.humans.find((h) => h.id === "h-op")!);
    expect(onBehalfOf(sentinel, operator).level).toBe("internal");
  });
});

describe("readiness", () => {
  it("computes readiness and status", () => {
    expect(readinessOf([{ key: "a", label: "", satisfiedBy: "f" }, { key: "b", label: "", satisfiedBy: null }])).toBe(50);
    expect(statusOf(100, new Date(SEED_NOW + DAY).toISOString(), SEED_NOW)).toBe("green");
    expect(statusOf(50, new Date(SEED_NOW + 3 * DAY).toISOString(), SEED_NOW)).toBe("red");
  });
  it("escalates at 21, 14, 7 and 2 days", () => {
    expect(escalationLevel(new Date(SEED_NOW + 21 * DAY).toISOString(), SEED_NOW)).toBe(1);
    expect(escalationLevel(new Date(SEED_NOW + 6 * DAY).toISOString(), SEED_NOW)).toBe(3);
  });
});
