// Workflow Studio: the chat intent engine, the Edit Review Agent and the authority rules.
import { describe, expect, it } from "vitest";
import type { ChatReply } from "@/contracts";
import { OPS, type Ctx } from "@/lib/mock/ops";
import { SEED_NOW } from "@/lib/mock/prng";
import { buildFinebase } from "@/lib/mock/seed/build";
import { chat } from "@/lib/mock/studio/chat";
import { healthOf, review, workflowsUsingTool } from "@/lib/mock/studio/engine";
import type { TenantData } from "@/lib/mock/types";

const as = (d: TenantData, id: string): Ctx => {
  const h = d.humans.find((x) => x.id === id)!;
  return { now: SEED_NOW, actor: { kind: "human", id: h.id, name: h.name } };
};
const human = (d: TenantData, id: string) => d.humans.find((h) => h.id === id)!;
const say = (d: TenantData, workflowId: string, message: string, persona = "h-founder", focus: ChatReply["focus"] = null) => chat(d, human(d, persona), { workflowId, message, focus, history: [] });

describe("studio seed", () => {
  it("gives each workflow its own members and shares only tools", () => {
    const d = buildFinebase();
    expect(d.studio.workflows.length).toBeGreaterThanOrEqual(12);
    const owners = new Map<string, number>();
    for (const w of d.studio.workflows) for (const m of w.members) owners.set(m, (owners.get(m) ?? 0) + 1);
    expect([...owners.values()].every((n) => n === 1)).toBe(true);
    expect(d.studio.items.filter((i) => i.kind === "tool").every((t) => t.workflowId === null)).toBe(true);
    expect(workflowsUsingTool(d.studio, "tool:inbox.reply").length).toBeGreaterThan(2);
    expect(d.studio.revisions.filter((r) => r.targetId === "refunds.policy.refund-window").length).toBe(3);
  });
});

describe("studio chat", () => {
  it("turns a vague request into a concrete, reviewed proposal with history cards", () => {
    const d = buildFinebase();
    const r = say(d, "wf-refunds", "make the refund window stricter");
    expect(r.proposal?.input.targetId).toBe("refunds.policy.refund-window");
    expect(r.proposal?.changes[0].after).toBe("21 days");
    expect(r.cards.length).toBeGreaterThanOrEqual(3);
    expect(r.cards[0].current).toBe(true);
    expect(r.suggestions.length).toBeGreaterThan(0);
    expect(r.proposal?.review.criticality).toBe(3);
    expect(r.proposal?.review.authority.route).toBe("approval");
  });

  it("follows a skill to the policy that limits it when asked to make it stricter", () => {
    const d = buildFinebase();
    const r = say(d, "wf-care", "make goodwill credits stricter");
    expect(r.proposal?.input.targetId).toBe("care.policy.goodwill-credit");
    expect(r.suggestions.some((s) => s.input?.targetId === "care.policy.goodwill-credit")).toBe(true);
  });

  it("reads exact values and units", () => {
    const d = buildFinebase();
    const r = say(d, "wf-refunds", "lower the auto refund limit to 40,000");
    expect(r.proposal?.input.patch.fields?.["param.amountMinor"]).toBe(4_000_000);
  });

  it("creates a scheduler from natural time words and picks the skill", () => {
    const d = buildFinebase();
    const r = say(d, "wf-billing", "add a scheduler for receivables chasing every weekday at 8am");
    expect(r.proposal?.input.intent).toBe("create");
    expect(r.proposal?.input.patch.fields?.cron).toBe("0 8 * * 1-5");
    expect(r.proposal?.input.patch.fields?.target).toBe("billing.skill.billing-receivables");
  });

  it("flags deleting something others depend on as breaking and offers fixes", () => {
    const d = buildFinebase();
    const r = say(d, "wf-care", "delete the personal data masking policy");
    expect(r.proposal?.review.verdict).toBe("breaking");
    expect(r.proposal?.review.fixes.length).toBeGreaterThan(0);
    expect(r.proposal?.review.authority.route).toBe("approval");
  });

  it("reviews a shared tool change across every workflow that uses it", () => {
    const d = buildFinebase();
    const r = say(d, "wf-care", "lower the rate limit of support-inbox.reply to 10");
    expect(r.proposal?.review.otherWorkflows.length).toBeGreaterThan(1);
    expect(r.proposal?.review.criticality).toBeGreaterThanOrEqual(3);
  });

  it("edits descriptions and topics, and lets the owner apply low risk edits", () => {
    const d = buildFinebase();
    const t = say(d, "wf-meetings", "add topic demos to the meetings workflow", "h-founder");
    expect(t.proposal?.review.criticality).toBe(0);
    expect(t.proposal?.review.authority.route).toBe("apply");
    const res = OPS.studioApply(d, as(d, "h-founder"), { input: t.proposal!.input });
    expect(res.status).toBe("applied");
    expect(d.studio.workflows.find((w) => w.id === "wf-meetings")!.topics).toContain("demos");
    const desc = say(d, "wf-meetings", "rewrite the description of meeting arrangement");
    expect(desc.proposal?.changes[0].field).toBe("description");
  });

  it("keeps L3 to viewing and asks which item when a request is ambiguous", () => {
    const d = buildFinebase();
    const r = say(d, "wf-billing", "change the trigger of the skill", "h-op");
    expect(r.proposal).toBeNull();
    const p = say(d, "wf-refunds", "pause the refund agent", "h-op");
    expect(p.proposal?.review.authority.route).toBe("view_only");
    expect(() => OPS.studioApply(d, as(d, "h-op"), { input: p.proposal!.input })).toThrow(/L3/);
  });

  it("answers history and health questions", () => {
    const d = buildFinebase();
    const h = say(d, "wf-refunds", "what changed in the refund window?");
    expect(h.cards[0].title).toMatch(/v3/);
    const health = say(d, "wf-billing", "what is broken in this workflow?");
    expect(health.answer).toMatch(/Edit Review Agent|healthy|Nothing/);
  });
});

describe("studio routing", () => {
  it("sends a C3 policy change to approval and applies it when the change request merges", () => {
    const d = buildFinebase();
    const input = { intent: "update" as const, kind: "policy" as const, targetId: "refunds.policy.refund-window", workflowId: "wf-refunds", patch: { fields: { "param.days": 21 } } };
    const res = OPS.studioApply(d, as(d, "h-aiops"), { input });
    expect(res.status).toBe("routed");
    const cr = d.changeRequests.find((c) => c.id === res.changeRequestId)!;
    expect(cr.status).toBe("awaiting_approval");
    OPS.decide(d, as(d, "h-hcs"), { approvalId: cr.approvalId!, decision: "approve" });
    expect(cr.status).toBe("merged");
    expect(d.studio.items.find((i) => i.id === "refunds.policy.refund-window")!.fields["param.days"]).toBe(21);
    expect(d.studio.pending[0].status).toBe("applied");
  });

  it("refuses a breaking change until it is acknowledged", () => {
    const d = buildFinebase();
    const input = { intent: "delete" as const, kind: "tool" as const, targetId: "tool:inbox.reply", workflowId: "wf-care", patch: {} };
    expect(review(d, human(d, "h-founder"), input).review.verdict).toBe("breaking");
    expect(() => OPS.studioApply(d, as(d, "h-founder"), { input })).toThrow(/breaking/);
    expect(OPS.studioApply(d, as(d, "h-founder"), { input, acknowledgeBreaking: true }).status).toBe("routed");
  });

  it("finds real breaks after a delete and offers fixes that clear them", () => {
    const d = buildFinebase();
    const wf = d.studio.workflows.find((w) => w.id === "wf-care")!;
    expect(healthOf(d, wf).findings.filter((f) => f.severity === "break")).toHaveLength(0);
  });
});
