// The one Workflow Studio operation that changes data. Low risk edits apply at once; everything else
// becomes a change request carrying the Edit Review Agent's report, and applies when it merges.
import type { ApplyResult, Change, ChangeRequest, MemberKind, ProposalInput, StudioKind } from "@/contracts";
import { OpError, audit, commit, createChangeRequest, ensureBranch, humanOf, notify, runChecks, type Ctx } from "../ops";
import { iso } from "../prng";
import type { TenantData } from "../types";
import { StudioError, commitInput, review, workflowOf } from "./engine";

const CR_KIND: Record<StudioKind, ChangeRequest["kind"]> = {
  workflow: "fix", skill: "skill", policy: "policy", template: "template", agent: "security", tool: "security", sensor: "grant", scheduler: "fix", loop: "fix",
};

function slug(v: string) {
  return v.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 28);
}

function guard<T>(fn: () => T): T {
  try {
    return fn();
  } catch (e) {
    if (e instanceof StudioError) throw new OpError(e.message, e.status);
    throw e;
  }
}

export function studioApply(d: TenantData, ctx: Ctx, { input, acknowledgeBreaking = false, note = "" }: { input: ProposalInput; acknowledgeBreaking?: boolean; note?: string }): ApplyResult {
  const h = humanOf(d, ctx);
  if (h.tier === "L3") throw new OpError("L3 can view workflows and suggest edits, but cannot change them.", 403);
  const proposal = guard(() => review(d, h, input));
  const { review: rv } = proposal;
  if (rv.verdict === "breaking" && !acknowledgeBreaking) throw new OpError("The Edit Review Agent marked this breaking. Read the review and confirm before sending it.", 409);
  const wf = workflowOf(d.studio, input.kind === "workflow" ? input.targetId : input.workflowId);
  const label = { type: `studio.${input.kind}`, id: input.targetId ?? proposal.targetName, label: proposal.targetName };

  if (rv.authority.route === "apply") {
    const out = guard(() => commitInput(d, h, input, ctx.now, null));
    audit(d, ctx, `studio.${input.intent}`, { ...label, id: out.targetId }, rv.criticality, `${proposal.title}. ${rv.summary}${note ? ` Note: ${note}` : ""}`, wf ? `studio:${wf.id}` : null);
    return { status: "applied", targetId: out.targetId, revisionId: out.revisionId, changeRequestId: null, message: `Applied. ${proposal.targetName} is now live${wf ? ` in ${wf.name}` : ""}.` };
  }

  const pendingId = `sp-${(d.counter + 1).toString(36)}`;
  const branch = `sandbox/studio-${slug(proposal.targetName)}-${(d.counter + 1).toString(36)}`;
  ensureBranch(d, ctx, branch, proposal.title);
  const changes: Change[] = proposal.changes.map((c) => ({ op: input.intent === "create" ? "add" : input.intent === "delete" ? "remove" : "modify", nodeType: `studio.${input.kind}`, nodeId: input.targetId ?? pendingId, label: proposal.targetName, field: c.field, before: c.before, after: c.after }));
  if (!changes.length) changes.push({ op: input.intent === "delete" ? "remove" : "add", nodeType: `studio.${input.kind}`, nodeId: input.targetId ?? pendingId, label: proposal.targetName, field: null, before: null, after: null });
  const c = commit(d, ctx, branch, proposal.title, changes, rv.criticality);
  const memberKind = input.kind as MemberKind;
  const cr = createChangeRequest(d, ctx, {
    title: proposal.title, kind: CR_KIND[input.kind], branch, commits: [c],
    plainDiff: [rv.summary, ...proposal.changes.map((x) => `${x.label}: ${x.before ?? "empty"} → ${x.after ?? "empty"}`), ...rv.findings.filter((f) => f.severity !== "info").map((f) => `${f.severity === "break" ? "Breaks" : "Watch"}: ${f.text}`), ...(note ? [`Note from ${h.name}: ${note}`] : [])],
    changeKind: "skill_step_edit", touches: { money: false, personalData: false, publicContent: false, legalTax: memberKind === "policy" && (wf?.criticality ?? 0) >= 4, clusters: wf ? [wf.clusterId] : [] },
    dri: wf?.dri ?? h.id, correlationId: `studio:${pendingId}`,
  });
  cr.criticality = rv.criticality;
  cr.criticalityReasons = [...rv.criticalityReasons, `${rv.reviewer}: ${rv.verdict}`];
  d.studio.pending.unshift({ id: pendingId, changeRequestId: cr.id, workflowId: wf?.id ?? null, input, title: proposal.title, verdict: rv.verdict, criticality: rv.criticality, by: h.id, at: iso(ctx.now), status: "awaiting_approval" });
  runChecks(d, ctx, { changeRequestId: cr.id });
  if (wf && wf.dri !== h.id) notify(d, ctx, { to: wf.dri, title: `Studio change for ${wf.name}`, body: `${h.name} proposed: ${proposal.title}. Review verdict: ${rv.verdict}.`, href: `/l2/versioning/${cr.id}`, kind: "approval" });
  return { status: "routed", targetId: input.targetId ?? pendingId, revisionId: null, changeRequestId: cr.id, message: `Sent to ${rv.authority.approver} as change request ${cr.id}. It applies when approved.` };
}

/** Called when a studio change request merges. */
export function applyStudioPending(d: TenantData, ctx: Ctx, pendingId: string) {
  const p = d.studio.pending.find((x) => x.id === pendingId);
  if (!p || p.status !== "awaiting_approval") return;
  const drafter = d.humans.find((h) => h.id === p.by);
  if (!drafter) return;
  try {
    commitInput(d, drafter, p.input, ctx.now, p.changeRequestId);
    p.status = "applied";
  } catch {
    p.status = "rejected";
  }
}

/** Anyone, L3 included, can pass a reviewed proposal to the workflow DRI. Nothing changes until the DRI acts on it. */
export function studioSuggest(d: TenantData, ctx: Ctx, { input, note = "" }: { input: ProposalInput; note?: string }) {
  const h = humanOf(d, ctx);
  const proposal = guard(() => review(d, h, input));
  const wf = workflowOf(d.studio, input.kind === "workflow" ? input.targetId : input.workflowId);
  const to = wf?.dri ?? null;
  notify(d, ctx, { to, title: `Suggested edit for ${wf?.name ?? "a shared tool"}`, body: `${h.name} suggests: ${proposal.title}. Review verdict: ${proposal.review.verdict}, C${proposal.review.criticality}.${note ? ` Note: ${note}` : ""}`, href: `/studio?wf=${wf?.id ?? ""}`, kind: "info" });
  audit(d, ctx, "studio.suggested", { type: `studio.${input.kind}`, id: input.targetId ?? proposal.targetName, label: proposal.targetName }, proposal.review.criticality, proposal.title, wf ? `studio:${wf.id}` : null);
  return { status: "suggested", message: `Sent to ${d.humans.find((x) => x.id === to)?.name ?? "the DRI"} as a suggestion. They can confirm it from the studio.` };
}
