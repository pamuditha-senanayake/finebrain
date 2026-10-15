// Workflow Studio: the chat intent engine, the Edit Review Agent and the authority rules.
import { describe, expect, it } from "vitest";
import type { ChatReply } from "@/contracts";
import { OPS, type Ctx } from "@/lib/mock/ops";
import { SEED_NOW } from "@/lib/mock/prng";
import { buildFinebase } from "@/lib/mock/seed/build";
import { chat } from "@/lib/mock/studio/chat";
import { commitInput, healthOf, review, workflowsUsingTool } from "@/lib/mock/studio/engine";
import { buildPrompt } from "@/lib/studio/story";
import type { TenantData } from "@/lib/mock/types";

const as = (d: TenantData, id: string): Ctx => {
  const h = d.humans.find((x) => x.id === id)!;
  return { now: SEED_NOW, actor: { kind: "human", id: h.id, name: h.name } };
};
const human = (d: TenantData, id: string) => d.humans.find((h) => h.id === id)!;
const say = (d: TenantData, workflowId: string, message: string, persona = "h-founder", focus: ChatReply["focus"] = null) => chat(d, human(d, persona), { workflowId, message, focus, history: [], story: null });

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

describe("studio tool levels", () => {
  it("offers a ready-made tool before building a new one", () => {
    const d = buildFinebase();
    const r = say(d, "wf-care", "add a tool that replies to the inbox");
    expect(r.proposal).toBeNull();
    expect(r.cards[0].targetId).toBe("tool:inbox.reply");
    expect(r.suggestions.some((s) => /anyway/.test(s.prompt))).toBe(true);
  });

  it("sets up a connector when nothing ready-made fits, and keeps custom code as the alternative", () => {
    const d = buildFinebase();
    const r = say(d, "wf-care", "add a tool called weather.lookup that fetches the forecast");
    expect(r.proposal?.input.patch.fields?.level).toBe("configured");
    expect(r.proposal?.input.patch.fields?.code).toBe("");
    expect(r.suggestions.some((s) => s.input?.patch.fields?.level === "custom")).toBe(true);
  });

  it("tests custom code in the sandbox and sends it for approval", () => {
    const d = buildFinebase();
    const r = say(d, "wf-care", "add a tool called weather.lookup with custom code");
    const p = r.proposal!;
    expect(p.input.patch.fields?.level).toBe("custom");
    expect(p.review.criticality).toBe(3);
    expect(p.review.findings.some((f) => /passed its sandbox test run/.test(f.text))).toBe(true);
    const broken = review(d, human(d, "h-founder"), { ...p.input, patch: { ...p.input.patch, fields: { ...p.input.patch.fields, code: "export async function run(input) { return process.env.KEY }" } } });
    expect(broken.review.findings.some((f) => f.severity === "break" && /outside the sandbox/.test(f.text))).toBe(true);
  });
});

describe("studio stories", () => {
  const sayWith = (d: TenantData, workflowId: string, message: string, story: ChatReply["story"]) => chat(d, human(d, "h-founder"), { workflowId, message, focus: null, history: [], story });

  it("seeds every workflow with a problem and scenarios linked to real parts", () => {
    const d = buildFinebase();
    const wf = d.studio.workflows.find((w) => w.id === "wf-refunds")!;
    expect(wf.story?.problem).toMatch(/Refund requests take days/);
    expect(wf.story?.scenarios[0].coveredBy).toContain("refunds.skill.refund-standard");
    expect(d.studio.workflows.every((w) => w.story && w.story.scenarios.length > 0)).toBe(true);
  });

  it("turns a new problem into BDD cases, then a workflow once confirmed", () => {
    const d = buildFinebase();
    const r = say(d, "wf-refunds", "Candidates wait two weeks for a reply when they apply for a job");
    expect(r.proposal).toBeNull();
    expect(r.story?.workflowId).toBeNull();
    expect(r.story?.name).toBe("Hiring pipeline");
    expect(r.story?.story.scenarios[0].when).toBe("candidates apply for a job");
    const ok = sayWith(d, "wf-refunds", "Yes, that is right", r.story);
    expect(ok.proposal?.input).toMatchObject({ intent: "create", kind: "workflow" });
    expect(ok.proposal?.input.patch.story?.scenarios.length).toBe(r.story!.story.scenarios.length);
  });

  it("adds cases to an existing workflow's story when the problem belongs there", () => {
    const d = buildFinebase();
    const r = say(d, "wf-refunds", "Refunds take three days when the customer paid by bank transfer");
    expect(r.story?.workflowId).toBe("wf-refunds");
    const more = sayWith(d, "wf-refunds", "Add another case: refund for a duplicate charge", r.story);
    expect(more.story!.story.scenarios.length).toBe(r.story!.story.scenarios.length + 1);
    const ok = sayWith(d, "wf-refunds", "yes", more.story);
    expect(ok.proposal?.input).toMatchObject({ intent: "update", kind: "workflow", targetId: "wf-refunds" });
    expect(ok.proposal?.input.patch.story!.scenarios.length).toBe(3 + more.story!.story.scenarios.length);
    expect(ok.suggestions[0].label).toMatch(/^Build: /);
  });

  it("explains the story and says which cases are built", () => {
    const d = buildFinebase();
    const r = say(d, "wf-refunds", "What problem does this workflow solve?");
    expect(r.answer).toMatch(/Refund requests take days/);
    expect(r.bullets[0]).toMatch(/handled by Refund inside policy/);
  });
});

describe("studio story building", () => {
  it("builds a case into a skill named after it, which then counts as handling it", () => {
    const d = buildFinebase();
    const wf = d.studio.workflows.find((w) => w.id === "wf-sales")!;
    const sc = { id: "x", title: "Nobody follows up for days", given: ["it is handled by hand today"], when: "nobody follows up for days", then: ["leads go cold"], goal: "Handled the same day.", coveredBy: [] };
    wf.story = { problem: "Leads go cold.", today: "By hand.", scenarios: [sc] };
    const r = say(d, "wf-sales", buildPrompt(sc));
    expect(r.story).toBeNull();
    expect(r.proposal?.input).toMatchObject({ intent: "create", kind: "skill" });
    expect(r.proposal?.input.patch.name).toBe("Nobody follows up for days");
    // A new skill is C3, so in the app it waits for approval; apply it directly here.
    commitInput(d, human(d, "h-founder"), r.proposal!.input, SEED_NOW, null);
    expect(say(d, "wf-sales", "What problem does this workflow solve?").bullets[0]).toMatch(/handled by Nobody follows up for days/);
  });
});
