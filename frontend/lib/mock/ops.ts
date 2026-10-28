// Domain operations over one tenant's data. Pure functions of (data, context, args), so the seed,
// the mock API and the journal replay all run the exact same logic.
import type {
  Actor,
  Approval,
  AuditEvent,
  Change,
  ChangeRequest,
  Commit,
  Criticality,
  Digest,
  DigestItem,
  Document,
  Fact,
  Human,
  ImpactPreview,
  Notification,
  Policy,
  Skill,
  Touches,
} from "@/contracts";
import { approverFor, assessCriticality, canApprove, type ChangeKind } from "@/lib/governance/criticality";
import { readinessOf, statusOf } from "@/lib/governance/readiness";
import { DAY, HOUR, hashString, iso } from "./prng";
import { applyStudioPending, studioApply, studioSuggest } from "./studio/ops";
import { markTrendKnown } from "./trend-ops";
import type { TenantData } from "./types";

export type Ctx = { now: number; actor: Actor };

export class OpError extends Error {
  status: number;
  constructor(message: string, status = 400) {
    super(message);
    this.status = status;
  }
}

const NO_TOUCH: Touches = { money: false, personalData: false, publicContent: false, legalTax: false, clusters: [] };

export function nextId(d: TenantData, prefix: string) {
  d.counter += 1;
  return `${prefix}-${d.counter.toString(36)}`;
}

function must<T>(v: T | undefined | null, what: string): T {
  if (v == null) throw new OpError(`${what} not found`, 404);
  return v;
}

export function humanOf(d: TenantData, ctx: Ctx): Human {
  if (ctx.actor.kind !== "human") throw new OpError("Only a person can do this", 403);
  return must(d.humans.find((h) => h.id === ctx.actor.id), "Person");
}

export function audit(d: TenantData, ctx: Ctx, action: string, target: AuditEvent["target"], criticality: Criticality, detail: string, correlationId: string | null, env: AuditEvent["env"] = "production") {
  d.audit.unshift({ id: nextId(d, "au"), tenantId: d.tenant.id, at: iso(ctx.now), actor: ctx.actor, action, target, env, criticality, detail, correlationId });
}

export function notify(d: TenantData, ctx: Ctx, n: Omit<Notification, "id" | "tenantId" | "at" | "read">) {
  d.notifications.unshift({ ...n, id: nextId(d, "nt"), tenantId: d.tenant.id, at: iso(ctx.now), read: false });
}

function head(d: TenantData, branch: string) {
  return d.branches.find((b) => b.name === branch)?.head ?? null;
}

export function commit(d: TenantData, ctx: Ctx, branch: string, message: string, changes: Change[], criticality: Criticality, evidence: string[] = [], tag: string | null = null): Commit {
  const c: Commit = {
    id: `c${(hashString(`${message}${ctx.now}${d.counter}`) % 0xfffffff).toString(16).padStart(7, "0")}`,
    tenantId: d.tenant.id, branch, parentId: head(d, branch), author: ctx.actor, message, changes, criticality, evidence, createdAt: iso(ctx.now), tag,
  };
  d.counter += 1;
  d.commits.push(c);
  const b = d.branches.find((x) => x.name === branch);
  if (b) b.head = c.id;
  return c;
}

export function ensureBranch(d: TenantData, ctx: Ctx, name: string, description: string) {
  let b = d.branches.find((x) => x.name === name);
  if (!b) {
    b = { id: nextId(d, "br"), tenantId: d.tenant.id, name, env: "sandbox", base: "main", head: head(d, "main"), status: "open", description, createdBy: ctx.actor, createdAt: iso(ctx.now) };
    d.branches.push(b);
  }
  return b;
}

function slug(s: string) {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
}

export function createChangeRequest(
  d: TenantData,
  ctx: Ctx,
  args: { title: string; kind: ChangeRequest["kind"]; branch: string; commits: Commit[]; plainDiff: string[]; changeKind: ChangeKind; touches: Touches; dri: string; correlationId: string },
): ChangeRequest {
  const { level, reasons } = assessCriticality(args.changeKind, args.touches);
  const cr: ChangeRequest = {
    id: nextId(d, "cr"), tenantId: d.tenant.id, title: args.title, kind: args.kind, fromBranch: args.branch, toBranch: "main", commits: args.commits.map((c) => c.id),
    plainDiff: args.plainDiff, changes: args.commits.flatMap((c) => c.changes), impactPreview: null, tests: null, approvalId: null, status: "draft",
    criticality: level, criticalityReasons: reasons, drafter: ctx.actor, dri: args.dri, clusters: args.touches.clusters.length ? args.touches.clusters : ["finebase-platform"],
    createdAt: iso(ctx.now), mergedAt: null, coolingUntil: null, correlationId: args.correlationId,
  };
  d.changeRequests.unshift(cr);
  audit(d, ctx, "change_request.opened", { type: "change_request", id: cr.id, label: cr.title }, level, `Opened from ${args.branch}. ${reasons.join("; ")}.`, args.correlationId, "sandbox");
  return cr;
}

// ---------------------------------------------------------------- conversations and Skillify

export function takeover(d: TenantData, ctx: Ctx, { conversationId }: { conversationId: string }) {
  const h = humanOf(d, ctx);
  const conv = must(d.conversations.find((c) => c.id === conversationId), "Conversation");
  if (conv.status === "closed") throw new OpError("Conversation is closed");
  conv.status = "human";
  conv.takenOverBy = h.id;
  conv.messages.push({ id: nextId(d, "m"), from: "system", author: "Brain", text: `${h.name} took over from the ${d.agents.find((a) => a.id === conv.agentId)?.name ?? "agent"}.`, at: iso(ctx.now), citations: [] });
  conv.updatedAt = iso(ctx.now);
  const run = d.runs.find((r) => r.id === conv.runId);
  if (run?.escalation) run.escalation.assignee = h.id;
  audit(d, ctx, "conversation.taken_over", { type: "conversation", id: conv.id, label: conv.topic }, 1, `${h.name} took over`, `conv:${conv.id}`);
  return conv;
}

/** A person marks a run as wrong. The agent is accountable: the mistake is recorded, shown on the run and the agent, and its DRI is told. */
export function markRunWrong(d: TenantData, ctx: Ctx, { runId, note }: { runId: string; note: string }) {
  const h = humanOf(d, ctx);
  const run = must(d.runs.find((r) => r.id === runId), "Run");
  if (!note.trim()) throw new OpError("Say what went wrong");
  if (run.markedWrong) throw new OpError("Already marked wrong", 409);
  run.markedWrong = { by: h.id, at: iso(ctx.now), note: note.trim() };
  run.failureClass ??= "marked wrong";
  run.humanTouch = true;
  const agent = d.agents.find((a) => a.id === run.agentId);
  audit(d, ctx, "run.marked_wrong", { type: "run", id: run.id, label: run.subject }, 2, note.trim(), `run:${run.id}`);
  if (agent) notify(d, ctx, { to: agent.dri, title: `Marked wrong: ${run.subject}`, body: `${agent.name}. ${note.trim()}`, href: `/l3/runs/${run.id}`, kind: "info" });
  return run;
}

export function handback(d: TenantData, ctx: Ctx, { conversationId }: { conversationId: string }) {
  humanOf(d, ctx);
  const conv = must(d.conversations.find((c) => c.id === conversationId), "Conversation");
  conv.status = "agent";
  conv.messages.push({ id: nextId(d, "m"), from: "system", author: "Brain", text: "Handed back to the agent.", at: iso(ctx.now), citations: [] });
  conv.updatedAt = iso(ctx.now);
  audit(d, ctx, "conversation.handed_back", { type: "conversation", id: conv.id, label: conv.topic }, 1, "Handed back", `conv:${conv.id}`);
  return conv;
}

export function sendMessage(d: TenantData, ctx: Ctx, { conversationId, text }: { conversationId: string; text: string }) {
  const h = humanOf(d, ctx);
  const conv = must(d.conversations.find((c) => c.id === conversationId), "Conversation");
  if (conv.status !== "human" || conv.takenOverBy !== h.id) throw new OpError("Take over the conversation before replying", 409);
  if (!text.trim()) throw new OpError("Message is empty");
  conv.messages.push({ id: nextId(d, "m"), from: "human", author: h.name, text: text.trim(), at: iso(ctx.now), citations: [] });
  conv.updatedAt = iso(ctx.now);
  return conv;
}

export function closeConversation(d: TenantData, ctx: Ctx, { conversationId, note }: { conversationId: string; note: string }) {
  const h = humanOf(d, ctx);
  const conv = must(d.conversations.find((c) => c.id === conversationId), "Conversation");
  conv.status = "closed";
  conv.messages.push({ id: nextId(d, "m"), from: "system", author: "Brain", text: `Closed by ${h.name}${note ? `: ${note}` : ""}.`, at: iso(ctx.now), citations: [] });
  conv.updatedAt = iso(ctx.now);
  const run = d.runs.find((r) => r.id === conv.runId);
  if (run) {
    run.status = "succeeded";
    run.endedAt = iso(ctx.now);
    run.humanTouch = true;
  }
  audit(d, ctx, "conversation.closed", { type: "conversation", id: conv.id, label: conv.topic }, 1, note || "Resolved by a person", `conv:${conv.id}`);
  return conv;
}

/** Never do one off work: turn a human handled case into a draft skill on a new branch. */
export function skillify(d: TenantData, ctx: Ctx, { conversationId }: { conversationId: string }) {
  const h = humanOf(d, ctx);
  const conv = must(d.conversations.find((c) => c.id === conversationId), "Conversation");
  if (conv.status === "agent" && !conv.takenOverBy) throw new OpError("Skillify needs a case a person handled. Take over first.", 409);
  if (conv.skillifiedTo) return must(d.changeRequests.find((c) => c.id === conv.skillifiedTo), "Change request");
  const agent = must(d.agents.find((a) => a.id === conv.agentId), "Agent");
  const isRefund = agent.id === "a-refund";
  const skillId = isRefund ? "refund-late-annual" : `${slug(conv.topic)}-handling`;
  const name = isRefund ? "Late refund with DRI approval" : `Handle: ${conv.topic}`;
  const branchName = `sandbox/skillify-${conv.id}`;
  ensureBranch(d, ctx, branchName, `Skillify from ${conv.id}`);
  const humanReplies = conv.messages.filter((m) => m.from === "human").map((m) => m.text);
  const skill: Skill = {
    id: skillId, tenantId: d.tenant.id, name, version: 1, branch: branchName, status: "draft", clusterId: agent.clusterId,
    trigger: isRefund ? "Refund request outside the refund window or above the auto threshold" : `Request like: ${conv.topic}`,
    inputs: ["Customer message", "Purchase record", "Refund policy"],
    steps: [
      { id: `${skillId}-1`, kind: "retrieval", text: "Retrieve purchase, refund window and threshold valid now", tool: null },
      { id: `${skillId}-2`, kind: "judgment", text: isRefund ? "Confirm the reason and whether the product was used" : "Confirm the request details", tool: null },
      { id: `${skillId}-3`, kind: "tool", text: isRefund ? "Request DRI approval with a plain summary and the cited policy" : "Request approval when outside policy", tool: "tool:evidence.request" },
      { id: `${skillId}-4`, kind: "quality_gate", text: "Tone gate: no refund promise before approval", tool: null },
      { id: `${skillId}-5`, kind: "tool", text: humanReplies[0] ? `Reply using the handling pattern: "${humanReplies[0].slice(0, 80)}"` : "Reply with the decision", tool: "tool:inbox.reply" },
    ],
    tools: ["tool:inbox.reply", "tool:evidence.request"], policies: isRefund ? ["refund-window", "refund-auto-threshold"] : [], requiredCapabilities: ["reply:customer"],
    outputs: ["Approval request", "Reply"], templateFields: isRefund ? ["tpl-refund-register.outside"] : [],
    evalSuite: { id: `eval-${skillId}`, cases: 18, passRate: 0 }, health: { taskSuccess: 0, consistencyPassK: 0, k: 8, conformance: 0 },
    agentIds: [agent.id], dri: agent.dri, updatedAt: iso(ctx.now), origin: "skillify",
  };
  d.skills.push(skill);
  const c = commit(d, ctx, branchName, `Skillify ${conv.id}: ${name}`, [
    { op: "add", nodeType: "skill", nodeId: skillId, label: name, field: null, before: null, after: skill.trigger },
    { op: "add", nodeType: "resolver", nodeId: `rr-${skillId}`, label: `Route to ${name}`, field: null, before: null, after: `${skill.trigger} → ${agent.name}` },
  ], 3, [conv.id]);
  const cr = createChangeRequest(d, ctx, {
    title: `New skill: ${name}`, kind: "skill", branch: branchName, commits: [c],
    plainDiff: [`New skill "${name}" for the ${agent.name}.`, `It fires when: ${skill.trigger.toLowerCase()}.`, "It asks the DRI before any refund outside policy instead of escalating with no plan."],
    changeKind: "new_skill", touches: { ...NO_TOUCH, money: isRefund, clusters: [agent.clusterId] }, dri: agent.dri, correlationId: `conv:${conv.id}`,
  });
  conv.skillifiedTo = cr.id;
  conv.messages.push({ id: nextId(d, "m"), from: "system", author: "Brain", text: `Skillified by ${h.name}: draft skill on ${branchName}.`, at: iso(ctx.now), citations: [] });
  audit(d, ctx, "conversation.skillified", { type: "skill", id: skillId, label: name }, 3, `Draft skill on ${branchName}`, `conv:${conv.id}`, "sandbox");
  return cr;
}

// ---------------------------------------------------------------- change requests and approvals

function impactFor(d: TenantData, cr: ChangeRequest): ImpactPreview {
  const seed = hashString(cr.id);
  const change = cr.changes[0];
  if (cr.kind === "skill" && change?.nodeId === "refund-late-annual") {
    return { runsReplayed: 412, decisionsChanged: 37, predictedRisk: "medium", summary: "37 of the last 412 refund conversations would get a different decision: they go to the DRI with a summary instead of a plain escalation.", examples: [{ runId: "run-1042", before: "Escalated with no plan", after: "DRI approval requested with cited policy" }] };
  }
  if (cr.kind === "policy" && cr.changes.some((x) => x.nodeId.startsWith("refund-window"))) {
    return { runsReplayed: 412, decisionsChanged: 37, predictedRisk: "medium", summary: "Refund window changes from 30 to 14 days, valid from 1 November. 37 of the last 412 refund conversations would get a different decision.", examples: [{ runId: "run-1042", before: "Outside policy at 41 days", after: "Outside policy at 41 days (no change)" }] };
  }
  if (cr.kind === "website") {
    return { runsReplayed: 2140, decisionsChanged: 0, predictedRisk: "medium", summary: "Replay of 2,140 pricing page sessions: 312 rage clicks hit the old toggle. Predicted rage clicks fall by about 60%. Pricing page change needs L1.", examples: [] };
  }
  const relevant = d.runs.filter((r) => cr.changes.some((x) => r.skill.id === x.nodeId)).length || 80 + (seed % 300);
  const changed = Math.round(relevant * (0.02 + (seed % 9) / 100));
  return { runsReplayed: relevant, decisionsChanged: changed, predictedRisk: changed > relevant * 0.08 ? "medium" : "low", summary: `${changed} of the last ${relevant} replayed runs would get a different decision.`, examples: [] };
}

export function runChecks(d: TenantData, ctx: Ctx, { changeRequestId }: { changeRequestId: string }) {
  const cr = must(d.changeRequests.find((c) => c.id === changeRequestId), "Change request");
  if (!["draft", "changes_requested", "testing"].includes(cr.status)) throw new OpError(`Checks already ran. Status is ${cr.status}.`, 409);
  const seed = hashString(cr.id);
  const total = 18 + (seed % 30);
  cr.tests = { suite: `eval-${cr.changes[0]?.nodeId ?? cr.id}`, total, passed: total, failed: 0, passK: 0.86 + (seed % 12) / 100, k: 8, ranAt: iso(ctx.now) };
  cr.impactPreview = impactFor(d, cr);
  const draftSkill = d.skills.find((s) => s.branch === cr.fromBranch);
  if (draftSkill) {
    draftSkill.evalSuite.passRate = 1;
    draftSkill.health = { taskSuccess: 0.9, consistencyPassK: cr.tests.passK, k: 8, conformance: 0.88 };
  }
  audit(d, ctx, "change_request.tested", { type: "change_request", id: cr.id, label: cr.title }, cr.criticality, `Sandbox tests ${cr.tests.passed}/${cr.tests.total}. Replay: ${cr.impactPreview.summary}`, cr.correlationId, "sandbox");
  const req = approverFor(cr.criticality);
  if (req.automatic) {
    cr.status = "approved";
    mergeChangeRequest(d, ctx, cr);
    return cr;
  }
  cr.status = "awaiting_approval";
  const approval: Approval = {
    id: nextId(d, "apr"), tenantId: d.tenant.id, subject: { kind: "change_request", id: cr.id }, title: cr.title, summary: cr.plainDiff.join(" "), criticality: cr.criticality,
    requiredApprovers: { tier: req.tier, count: req.count, roles: [] }, votes: [], dueAt: iso(ctx.now + d.tenant.criticalityThresholds.approvalExpiryHours * HOUR), createdAt: iso(ctx.now),
    status: "pending", delegatedTo: null, dri: cr.dri, drafter: cr.drafter, evidence: cr.commits, correlationId: cr.correlationId,
  };
  d.approvals.unshift(approval);
  cr.approvalId = approval.id;
  notify(d, ctx, { to: req.tier === "L1" ? cr.dri : null, title: `C${cr.criticality} approval: ${cr.title}`, body: req.label, href: `/l1/approvals/${approval.id}`, kind: "approval" });
  return cr;
}

function applyChange(d: TenantData, ctx: Ctx, cr: ChangeRequest, change: Change) {
  if (change.nodeType === "skill") {
    const draft = d.skills.find((s) => s.id === change.nodeId && s.branch === cr.fromBranch);
    if (draft) {
      const live = d.skills.find((s) => s.id === change.nodeId && s.branch === "main");
      if (live) {
        live.status = "deprecated";
        draft.version = live.version + 1;
        d.skills = d.skills.filter((s) => s !== live);
      }
      draft.branch = "main";
      draft.status = "active";
      draft.updatedAt = iso(ctx.now);
      for (const agentId of draft.agentIds) {
        const agent = d.agents.find((a) => a.id === agentId);
        if (agent) agent.skills = [...agent.skills.filter((s) => s.id !== draft.id), { id: draft.id, version: draft.version, branch: "main" }];
      }
      if (!d.resolver.some((r) => r.skill.id === draft.id)) {
        d.resolver.unshift({ id: `rr-${draft.id}`, tenantId: d.tenant.id, event: draft.trigger, match: draft.name.toLowerCase(), skill: { id: draft.id, version: draft.version, branch: "main" }, agentId: draft.agentIds[0], priority: 1, triggerEval: { cases: draft.evalSuite.cases, passRate: 1, lastRunAt: iso(ctx.now) } });
      } else {
        for (const r of d.resolver) if (r.skill.id === draft.id) r.skill.version = draft.version;
      }
      if (!d.graph.nodes.some((n) => n.id === `n:skill:${draft.id}`)) {
        d.graph.nodes.push({ id: `n:skill:${draft.id}`, type: "skill", label: `${draft.name} v${draft.version}`, refId: draft.id, clusterId: draft.clusterId, sensitivity: "internal", requires: { capability: null, roles: [] }, x: 40, y: 20 });
        for (const a of draft.agentIds) d.graph.edges.push({ id: `e-${draft.id}-${a}`, source: `n:${a}`, target: `n:skill:${draft.id}`, kind: "uses", requiresCapability: null });
      }
    }
  } else if (change.nodeType === "policy") {
    const draft = d.policies.find((p) => p.key === change.nodeId && p.branch === cr.fromBranch);
    if (draft) {
      const live = d.policies.find((p) => p.key === draft.key && p.branch === "main" && !p.supersededBy);
      if (live) {
        live.supersededBy = draft.id;
        live.validTo = live.validTo ?? draft.validFrom;
      }
      draft.branch = "main";
      draft.recordedAt = iso(ctx.now);
      const node = d.graph.nodes.find((n) => n.id === `n:policy:${draft.key}`);
      if (node) node.label = `${draft.name} v${draft.version}`;
    }
  } else if (change.nodeType === "fact") {
    const f = d.facts.find((x) => x.id === change.nodeId);
    if (f && change.field === "status" && change.after) f.status = change.after as Fact["status"];
    if (f && change.field === "validTo") f.validTo = change.after;
    if (f && change.field === "verifiedBy") f.verifiedBy = change.after;
    if (f) f.recordedAt = iso(ctx.now);
  } else if (change.nodeType === "agent" && change.field === "capabilities") {
    const agent = d.agents.find((a) => a.id === change.nodeId);
    if (agent && change.after) {
      const caps = change.after.replace(/\([^)]*\)/g, "").split(",").map((s) => s.trim()).filter(Boolean);
      agent.capabilities = [...new Set([...agent.capabilities, ...caps])];
    }
  } else if (change.nodeType === "agent" && change.field === "autonomy") {
    const agent = d.agents.find((a) => a.id === change.nodeId);
    if (agent && change.after) {
      agent.autonomy = change.after as typeof agent.autonomy;
      agent.training.push({ at: iso(ctx.now), event: `Promoted to ${change.after}`, by: ctx.actor.id });
    }
  } else if (change.nodeType === "template") {
    const t = d.templates.find((x) => x.id === change.nodeId);
    const field = t?.fields.find((f) => f.key === change.field);
    if (field && change.after) {
      field.value = change.after;
      field.filledAt = iso(ctx.now);
      field.filledBy = ctx.actor.id;
    }
  } else if (change.nodeType === "document" && change.field === "status") {
    d.documents = d.documents.filter((x) => x.id !== change.nodeId || change.after !== "archived");
  }
}

export function mergeChangeRequest(d: TenantData, ctx: Ctx, cr: ChangeRequest) {
  if (cr.coolingUntil && Date.parse(cr.coolingUntil) > ctx.now) throw new OpError("Cooling period has not ended", 409);
  const conflict = d.changeRequests.find((o) => o.id !== cr.id && o.status === "merged" && o.mergedAt && o.mergedAt > cr.createdAt && o.changes.some((x) => cr.changes.some((y) => y.nodeId === x.nodeId && y.nodeType === x.nodeType && x.op !== "add")));
  if (conflict && cr.changes.some((x) => x.op === "modify")) {
    cr.status = "conflict";
    audit(d, ctx, "change_request.conflict", { type: "change_request", id: cr.id, label: cr.title }, cr.criticality, `Conflicts with ${conflict.id}`, cr.correlationId);
    return cr;
  }
  for (const change of cr.changes) applyChange(d, ctx, cr, change);
  const merged = d.commits.filter((c) => c.branch === "main" && c.tag?.startsWith(`release-${iso(ctx.now).slice(0, 10)}`)).length;
  const c = commit(d, ctx, "main", `Merge ${cr.fromBranch}: ${cr.title}`, cr.changes, cr.criticality, cr.commits, `release-${iso(ctx.now).slice(0, 10)}.${merged + 1}`);
  cr.status = "merged";
  cr.mergedAt = iso(ctx.now);
  const b = d.branches.find((x) => x.name === cr.fromBranch);
  if (b && b.status === "open") b.status = "merged";
  audit(d, ctx, "change_request.merged", { type: "change_request", id: cr.id, label: cr.title }, cr.criticality, `Merged to main as ${c.id} (${c.tag}). Now live in Production.`, cr.correlationId);
  if (cr.correlationId.startsWith("studio:")) applyStudioPending(d, ctx, cr.correlationId.slice("studio:".length));
  for (const exp of d.experiments) if (exp.changeRequestId === cr.id) exp.status = "kept";
  for (const item of d.librarian) if (item.changeRequestId === cr.id) item.status = "resolved";
  return cr;
}

export function decide(d: TenantData, ctx: Ctx, args: { approvalId: string; decision: "approve" | "reject" | "request_changes" | "delegate"; comment?: string; delegateTo?: string | null }) {
  const h = humanOf(d, ctx);
  const ap = must(d.approvals.find((a) => a.id === args.approvalId), "Approval");
  if (ap.status !== "pending") throw new OpError(`This approval is ${ap.status}`, 409);
  if (Date.parse(ap.dueAt) < ctx.now) {
    ap.status = "expired";
    throw new OpError("This approval expired. Ask the drafter to resubmit.", 409);
  }
  const comment = args.comment ?? "";
  if (args.decision === "delegate") {
    const to = must(d.humans.find((x) => x.id === args.delegateTo), "Delegate");
    if (to.tier !== ap.requiredApprovers.tier && !(to.tier === "L1")) throw new OpError(`Delegate must be ${ap.requiredApprovers.tier}`, 400);
    ap.delegatedTo = to.id;
    ap.votes.push({ by: h.id, at: iso(ctx.now), decision: "delegate", comment: comment || `Delegated to ${to.name}` });
    notify(d, ctx, { to: to.id, title: `Delegated to you: ${ap.title}`, body: `From ${h.name}`, href: `/l1/approvals/${ap.id}`, kind: "approval" });
    audit(d, ctx, "approval.delegated", { type: "approval", id: ap.id, label: ap.title }, ap.criticality, `Delegated to ${to.name}`, ap.correlationId);
    return ap;
  }
  if (args.decision === "approve") {
    const approvedBy = ap.votes.filter((v) => v.decision === "approve").map((v) => v.by);
    const why = canApprove({ id: h.id, tier: h.tier, maxApprovalCriticality: h.maxApprovalCriticality }, ap.criticality, approvedBy);
    if (why) throw new OpError(why, 403);
    if (ap.drafter.kind === "human" && ap.drafter.id === h.id) throw new OpError("You drafted this change. Someone else must approve it.", 403);
    const subjectCr = ap.subject.kind === "change_request" ? d.changeRequests.find((c) => c.id === ap.subject.id) : null;
    if (subjectCr && (!subjectCr.tests || !subjectCr.impactPreview)) throw new OpError("Nothing goes live blind: run sandbox tests and the replay first.", 409);
    ap.votes.push({ by: h.id, at: iso(ctx.now), decision: "approve", comment });
    const count = new Set([...approvedBy, h.id]).size;
    audit(d, ctx, "approval.approved", { type: "approval", id: ap.id, label: ap.title }, ap.criticality, `${h.name} approved (${count} of ${ap.requiredApprovers.count})${comment ? `: ${comment}` : ""}`, ap.correlationId);
    if (count < ap.requiredApprovers.count) {
      notify(d, ctx, { to: null, title: `Second L1 approval needed: ${ap.title}`, body: `${h.name} approved. The two person rule needs one more.`, href: `/l1/approvals/${ap.id}`, kind: "approval" });
      return ap;
    }
    ap.status = "approved";
    applyApprovedSubject(d, ctx, ap);
    return ap;
  }
  ap.votes.push({ by: h.id, at: iso(ctx.now), decision: args.decision, comment });
  ap.status = args.decision === "reject" ? "rejected" : "changes_requested";
  if (ap.subject.kind === "change_request") {
    const cr = d.changeRequests.find((c) => c.id === ap.subject.id);
    if (cr) cr.status = args.decision === "reject" ? "rejected" : "changes_requested";
  }
  if (ap.subject.kind === "grant") {
    const g = d.grants.find((x) => x.id === ap.subject.id);
    if (g) g.status = "revoked";
  }
  audit(d, ctx, `approval.${args.decision}`, { type: "approval", id: ap.id, label: ap.title }, ap.criticality, comment || args.decision, ap.correlationId);
  return ap;
}

function applyApprovedSubject(d: TenantData, ctx: Ctx, ap: Approval) {
  if (ap.subject.kind === "change_request") {
    const cr = must(d.changeRequests.find((c) => c.id === ap.subject.id), "Change request");
    cr.status = "approved";
    mergeChangeRequest(d, ctx, cr);
  } else if (ap.subject.kind === "grant") {
    activateGrant(d, ctx, ap.subject.id);
  }
}

export function rollback(d: TenantData, ctx: Ctx, { commitId }: { commitId: string }) {
  const h = humanOf(d, ctx);
  if (h.tier === "L3") throw new OpError("Rollback needs L2 or L1", 403);
  const target = must(d.commits.find((c) => c.id === commitId && c.branch === "main"), "Commit on main");
  const later = d.commits.filter((c) => c.branch === "main" && c.createdAt > target.createdAt);
  const changes: Change[] = later.flatMap((c) => c.changes).map((x) => ({ ...x, op: x.op === "add" ? "remove" : x.op === "remove" ? "add" : "modify", before: x.after, after: x.before }));
  for (const x of later.flatMap((c) => c.changes)) {
    if (x.nodeType === "skill" && x.op === "add") {
      const s = d.skills.find((sk) => sk.id === x.nodeId);
      if (s) s.status = "deprecated";
      d.resolver = d.resolver.filter((r) => r.skill.id !== x.nodeId);
    }
    if (x.nodeType === "agent" && x.field === "capabilities" && x.before) {
      const agent = d.agents.find((a) => a.id === x.nodeId);
      if (agent) agent.capabilities = x.before.split(",").map((s) => s.trim());
    }
  }
  const c = commit(d, ctx, "main", `Rollback to ${target.id}`, changes, 3, [target.id]);
  audit(d, ctx, "main.rolled_back", { type: "commit", id: c.id, label: `Rollback to ${target.id}` }, 3, `Reverted ${later.length} commits`, null);
  return c;
}

// ---------------------------------------------------------------- readiness, evidence and grants

export function runReadinessScheduler(d: TenantData, ctx: Ctx) {
  const created: string[] = [];
  d.gaps = [];
  for (const ob of d.obligations) {
    const daysLeft = (Date.parse(ob.dueAt) - ctx.now) / DAY;
    for (const item of ob.requiredEvidence.filter((i) => !i.satisfiedBy)) {
      const open = d.evidenceRequests.find((r) => r.obligationId === ob.id && r.evidenceKey === item.key && r.status !== "expired");
      const action = daysLeft <= 21 ? (ob.id === "ob-vat-sep" && item.key === "input-invoices" ? "request_grant" : "request_dri") : "dispatch_agent";
      const gap = { id: nextId(d, "gap"), target: { kind: "obligation" as const, id: ob.id, label: ob.title }, missing: item.label, dueAt: ob.dueAt, action: action as "dispatch_agent" | "request_dri" | "request_grant", dri: ob.dri, escalationDays: [21, 14, 7, 2], requestId: open?.id ?? null };
      d.gaps.push(gap);
      if (open || action === "dispatch_agent") continue;
      const req = {
        id: nextId(d, "er"), tenantId: d.tenant.id, obligationId: ob.id, evidenceKey: item.key, item: `${item.label} (${ob.title})`, requestedFrom: ob.dri, status: "open" as const,
        dueAt: ob.prepareBy, createdAt: iso(ctx.now), escalationLevel: [21, 14, 7, 2].filter((x) => daysLeft <= x).length,
        suggestedGrant: action === "request_grant" ? { source: "Finance inbox (finance@finebase.lk)", scope: "Read messages with supplier invoice attachments, September 2026 only", retentionDays: 90, agents: ["a-compliance"], revoke: "Revoke any time in Security and access. Access ends automatically after 90 days." } : null,
        fulfilledBy: null,
      };
      d.evidenceRequests.unshift(req);
      gap.requestId = req.id;
      created.push(req.id);
      notify(d, ctx, { to: ob.dri, title: `Evidence needed: ${item.label}`, body: `${ob.title} is due in ${Math.ceil(daysLeft)} days (sample).`, href: "/l1/digest?tab=evidence", kind: "evidence" });
      audit(d, ctx, "evidence.requested", { type: "obligation", id: ob.id, label: ob.title }, 4, `Requested "${item.label}" from the DRI ${Math.ceil(daysLeft)} days before the sample deadline`, `ob:${ob.id}`);
    }
  }
  for (const r of d.readinessRules) r.lastRunAt = iso(ctx.now);
  return { gaps: d.gaps.length, requestsCreated: created.length };
}

function satisfyEvidence(d: TenantData, ctx: Ctx, obligationId: string, key: string, factId: string) {
  const ob = must(d.obligations.find((o) => o.id === obligationId), "Obligation");
  const item = must(ob.requiredEvidence.find((i) => i.key === key), "Evidence item");
  item.satisfiedBy = factId;
  ob.readiness = readinessOf(ob.requiredEvidence);
  ob.status = statusOf(ob.readiness, ob.dueAt, ctx.now);
  if (ob.status === "green") audit(d, ctx, "obligation.ready", { type: "obligation", id: ob.id, label: ob.title }, 4, "Readiness is green. A human still files.", `ob:${ob.id}`);
}

function evidenceFact(d: TenantData, ctx: Ctx, req: { id: string; item: string; obligationId: string }, doc: Document, verifiedBy: string): Fact {
  const f: Fact = {
    id: nextId(d, "f"), tenantId: d.tenant.id, clusterId: "finance-compliance", statement: `${req.item} received`, subject: req.obligationId, value: doc.title,
    validFrom: iso(ctx.now), validTo: null, recordedAt: iso(ctx.now), evidence: [{ documentId: doc.id, page: 1, quote: `Provided as evidence for ${req.item}` }],
    verifiedBy, status: "verified", sensitivity: "restricted", dependents: [{ type: "obligation", id: req.obligationId, label: req.item }],
  };
  d.facts.unshift(f);
  doc.linkedFacts.push(f.id);
  d.graph.nodes.push({ id: `n:fact:${f.id}`, type: "fact", label: f.statement.slice(0, 46), refId: f.id, clusterId: f.clusterId, sensitivity: "restricted", requires: { capability: null, roles: ["finance"] }, x: 60, y: 60 });
  d.graph.nodes.push({ id: `n:doc:${doc.id}`, type: "document", label: doc.title, refId: doc.id, clusterId: doc.clusterId, sensitivity: doc.sensitivity, requires: { capability: null, roles: ["finance"] }, x: 70, y: 70 });
  d.graph.edges.push({ id: `e-${f.id}`, source: `n:doc:${doc.id}`, target: `n:fact:${f.id}`, kind: "evidences", requiresCapability: null });
  return f;
}

export function uploadEvidence(d: TenantData, ctx: Ctx, { requestId, fileName, sizeKb }: { requestId: string; fileName: string; sizeKb: number }) {
  const h = humanOf(d, ctx);
  const req = must(d.evidenceRequests.find((r) => r.id === requestId), "Evidence request");
  if (req.status === "fulfilled") throw new OpError("Already fulfilled", 409);
  const doc: Document = {
    id: nextId(d, "doc"), tenantId: d.tenant.id, clusterId: "finance-compliance", title: fileName, source: "Upload by DRI", type: "evidence", sensitivity: "restricted", extractionStatus: "done",
    linkedFacts: [], retentionDays: 2555, filingRule: "finance-records", uploadedBy: h.id, uploadedAt: iso(ctx.now), sizeKb: Math.max(1, Math.round(sizeKb)), personalData: false,
  };
  d.documents.unshift(doc);
  const f = evidenceFact(d, ctx, req, doc, h.id);
  req.status = "fulfilled";
  req.fulfilledBy = { kind: "upload", ref: doc.id };
  satisfyEvidence(d, ctx, req.obligationId, req.evidenceKey, f.id);
  audit(d, ctx, "evidence.uploaded", { type: "document", id: doc.id, label: fileName }, 4, `Filed under finance-records. Fact ${f.id} recorded with provenance.`, `ob:${req.obligationId}`);
  return { request: req, fact: f, document: doc };
}

export function requestGrant(d: TenantData, ctx: Ctx, { requestId }: { requestId: string }) {
  const h = humanOf(d, ctx);
  const req = must(d.evidenceRequests.find((r) => r.id === requestId), "Evidence request");
  const g = must(req.suggestedGrant, "Suggested grant");
  const grant = { id: nextId(d, "g"), tenantId: d.tenant.id, source: g.source, scope: g.scope, retentionDays: g.retentionDays, agents: g.agents, revoke: g.revoke, status: "pending" as const, requestedBy: h.id, approvalId: null as string | null, createdAt: iso(ctx.now) };
  d.grants.unshift(grant);
  const { level, reasons } = assessCriticality("inbox_access_grant", { ...NO_TOUCH, legalTax: true, clusters: ["finance-compliance"] });
  const req2 = approverFor(level);
  const ap: Approval = {
    id: nextId(d, "apr"), tenantId: d.tenant.id, subject: { kind: "grant", id: grant.id }, title: `Grant ${g.agents.map((a) => d.agents.find((x) => x.id === a)?.name ?? a).join(", ")} read access: ${g.source}`,
    summary: `${g.scope}. Retained ${g.retentionDays} days. ${g.revoke} ${reasons.join("; ")}.`, criticality: level, requiredApprovers: { tier: req2.tier, count: req2.count, roles: [] }, votes: [],
    dueAt: iso(ctx.now + 72 * HOUR), createdAt: iso(ctx.now), status: "pending", delegatedTo: null, dri: req.requestedFrom, drafter: { kind: "agent", id: "a-compliance", name: "Compliance Agent" }, evidence: [req.id], correlationId: `ob:${req.obligationId}`,
  };
  d.approvals.unshift(ap);
  grant.approvalId = ap.id;
  req.status = "awaiting_grant_approval";
  notify(d, ctx, { to: null, title: "C4: grant finance inbox access", body: "Two L1 approvers needed", href: `/l1/approvals/${ap.id}`, kind: "approval" });
  audit(d, ctx, "grant.requested", { type: "grant", id: grant.id, label: g.source }, level, g.scope, `ob:${req.obligationId}`);
  return { grant, approval: ap };
}

function activateGrant(d: TenantData, ctx: Ctx, grantId: string) {
  const grant = must(d.grants.find((g) => g.id === grantId), "Grant");
  grant.status = "active";
  for (const a of grant.agents) {
    const agent = d.agents.find((x) => x.id === a);
    if (agent && grant.source.startsWith("Finance inbox")) agent.capabilities = [...new Set([...agent.capabilities, "finance:read"])];
  }
  const sensor = d.sensors.find((s) => s.id === "s-finance-inbox");
  if (sensor && grant.source.startsWith("Finance inbox")) {
    sensor.health = "ok";
    sensor.scopes = [grant.scope];
    sensor.retentionDays = grant.retentionDays;
  }
  audit(d, ctx, "grant.activated", { type: "grant", id: grant.id, label: grant.source }, 4, `${grant.scope}. Revocable.`, null);
  // The Compliance Agent now fetches what was missing.
  const req = d.evidenceRequests.find((r) => r.status === "awaiting_grant_approval" && r.suggestedGrant?.source === grant.source);
  if (req) {
    const agentCtx: Ctx = { now: ctx.now, actor: { kind: "agent", id: "a-compliance", name: "Compliance Agent" } };
    const doc: Document = { id: nextId(d, "doc"), tenantId: d.tenant.id, clusterId: "finance-compliance", title: "Supplier invoices September 2026 (from finance inbox).zip", source: "Finance inbox via grant", type: "evidence", sensitivity: "restricted", extractionStatus: "done", linkedFacts: [], retentionDays: grant.retentionDays, filingRule: "finance-records", uploadedBy: "a-compliance", uploadedAt: iso(ctx.now), sizeKb: 2480, personalData: false };
    d.documents.unshift(doc);
    const f = evidenceFact(d, agentCtx, req, doc, "a-compliance");
    req.status = "fulfilled";
    req.fulfilledBy = { kind: "grant", ref: grant.id };
    satisfyEvidence(d, agentCtx, req.obligationId, req.evidenceKey, f.id);
    audit(d, agentCtx, "evidence.fetched", { type: "document", id: doc.id, label: doc.title }, 4, "Fetched under the new grant", `ob:${req.obligationId}`);
  }
}

export function revokeGrant(d: TenantData, ctx: Ctx, { grantId }: { grantId: string }) {
  humanOf(d, ctx);
  const grant = must(d.grants.find((g) => g.id === grantId), "Grant");
  grant.status = "revoked";
  for (const a of grant.agents) {
    const agent = d.agents.find((x) => x.id === a);
    if (agent && grant.source.startsWith("Finance inbox")) agent.capabilities = agent.capabilities.filter((c) => c !== "finance:read");
  }
  if (grant.source.startsWith("Finance inbox")) {
    const sensor = d.sensors.find((s) => s.id === "s-finance-inbox");
    if (sensor) {
      sensor.health = "down";
      sensor.scopes = ["not granted"];
    }
  }
  audit(d, ctx, "grant.revoked", { type: "grant", id: grant.id, label: grant.source }, 3, "Revoked", null);
  return grant;
}

// ---------------------------------------------------------------- librarian

export function librarianPropose(d: TenantData, ctx: Ctx, { itemId }: { itemId: string }) {
  const item = must(d.librarian.find((i) => i.id === itemId), "Librarian item");
  if (item.status !== "open") throw new OpError("Already proposed", 409);
  const lib: Ctx = { now: ctx.now, actor: { kind: "agent", id: "a-librarian", name: "Librarian" } };
  const branchName = `sandbox/librarian-${item.id.replace("lib-", "")}`;
  ensureBranch(d, lib, branchName, item.title);
  let cr: ChangeRequest;
  if (item.id === "lib-refund-window") {
    const live = must(d.policies.find((p) => p.key === "refund-window" && !p.supersededBy), "Policy");
    const newFrom = "2026-11-01T00:00:00Z";
    const draft: Policy = { ...structuredClone(live), id: `refund-window@v${live.version + 1}`, version: live.version + 1, branch: branchName, statement: "Annual plans: refunds within 14 days of purchase. Monthly plans: 30 days.", rule: { kind: live.rule.kind, params: { days: 14, monthlyDays: 30 } }, validFrom: newFrom, validTo: null, recordedAt: iso(ctx.now), supersededBy: null, evidence: ["doc-pricing-oct-2026"], freshness: { intervalClosed: false, driftPointAt: null, conformance: 0.93, conflictingEvidence: 0, outdatedRelianceRate: 0 } };
    d.policies.push(draft);
    const dependents = live.dependents.map((x) => ({ type: x.type, id: x.id, label: x.label }));
    const changes: Change[] = [
      { op: "modify", nodeType: "policy", nodeId: "refund-window", label: "Refund window", field: "rule.days", before: "30 days (v3, valid from 1 Jan 2026)", after: "14 days for annual plans (v4, valid from 1 Nov 2026)" },
      { op: "modify", nodeType: "fact", nodeId: "f-refund-window", label: "Refund window fact", field: "validTo", before: null, after: newFrom },
      { op: "modify", nodeType: "fact", nodeId: "f-pricing-oct-refund", label: "October pricing sheet fact", field: "status", before: "conflicted", after: "verified" },
      ...dependents.map((dep): Change => ({ op: "modify", nodeType: dep.type, nodeId: dep.id, label: dep.label, field: "references", before: "refund-window v3", after: "refund-window v4" })),
    ];
    const c = commit(d, lib, branchName, "Librarian: refund window 30 → 14 days for annual plans from 1 November", changes, 3, ["doc-pricing-oct-2026", "f-pricing-oct-refund"]);
    item.proposal = { winningSource: "Pricing sheet October 2026.pdf (newer, signed off by the founder)", newValidFrom: newFrom, dependents };
    cr = createChangeRequest(d, lib, {
      title: "Invalidate refund window v3, add v4 (14 days for annual plans from 1 November)", kind: "policy", branch: branchName, commits: [c],
      plainDiff: ["Refund window changes from 30 to 14 days for annual plans, valid from 1 November.", "v3 stays true until 31 October. Nothing is deleted: v3 gets a closed validity interval.", `All ${dependents.length} dependents are updated in this one change: ${dependents.map((x) => x.label).join(", ")}.`],
      changeKind: "ground_truth_change", touches: { ...NO_TOUCH, money: true, publicContent: true, clusters: ["finebase-platform"] }, dri: "h-hcs", correlationId: `lib:${item.id}`,
    });
  } else {
    const fid = item.factIds[item.factIds.length - 1];
    const changes: Change[] = item.kind === "orphan"
      ? [{ op: "modify", nodeType: "document", nodeId: item.documentId ?? "", label: "Archive orphan document", field: "status", before: "active", after: "archived" }]
      : [{ op: "modify", nodeType: "fact", nodeId: fid, label: d.facts.find((f) => f.id === fid)?.statement ?? fid, field: "status", before: d.facts.find((f) => f.id === fid)?.status ?? null, after: item.kind === "duplicate" ? "superseded" : item.kind === "stale" ? "stale" : "verified" }];
    const c = commit(d, lib, branchName, `Librarian: resolve ${item.kind} – ${item.title}`, changes, item.kind === "orphan" ? 1 : 3);
    item.proposal = { winningSource: item.documentId ?? "ground truth", newValidFrom: iso(ctx.now), dependents: [] };
    cr = createChangeRequest(d, lib, { title: `Librarian: ${item.title}`, kind: "fact", branch: branchName, commits: [c], plainDiff: [`Resolve ${item.kind}: ${item.title}.`], changeKind: item.kind === "orphan" ? "faq_wording" : "ground_truth_change", touches: NO_TOUCH, dri: "h-ks", correlationId: `lib:${item.id}` });
  }
  item.status = "proposed";
  item.changeRequestId = cr.id;
  return cr;
}

// ---------------------------------------------------------------- website loop experiments

export function experimentPreview(d: TenantData, ctx: Ctx, { experimentId }: { experimentId: string }) {
  const exp = must(d.experiments.find((e) => e.id === experimentId), "Experiment");
  if (exp.status !== "proposed") throw new OpError("Already previewed", 409);
  const ins: Ctx = { now: ctx.now, actor: { kind: "agent", id: "a-insights", name: "Insights Agent" } };
  const branchName = `sandbox/${exp.id}`;
  ensureBranch(d, ins, branchName, exp.title);
  commit(d, ins, branchName, `Experiment ${exp.id}: ${exp.variants[1]?.name}`, [{ op: "modify", nodeType: "web_page", nodeId: "web:/pricing#toggle", label: "Pricing page toggle", field: "component", before: "Toggle: Monthly | Annual (save 17%)", after: "Segmented control: Monthly | Annual · save LKR 48,000" }], 3);
  exp.branch = branchName;
  exp.status = "previewed";
  audit(d, ins, "experiment.previewed", { type: "experiment", id: exp.id, label: exp.title }, 2, `Sandbox branch ${branchName} with impact preview`, `exp:${exp.id}`, "sandbox");
  return exp;
}

export function experimentStart(d: TenantData, ctx: Ctx, { experimentId }: { experimentId: string }) {
  const h = humanOf(d, ctx);
  const exp = must(d.experiments.find((e) => e.id === experimentId), "Experiment");
  if (exp.status !== "previewed") throw new OpError("Preview on a sandbox branch first", 409);
  if (h.tier === "L3") throw new OpError("Starting an experiment needs L2 or L1", 403);
  exp.status = "running";
  exp.startedAt = iso(ctx.now);
  audit(d, ctx, "experiment.started", { type: "experiment", id: exp.id, label: exp.title }, 2, "A/B split 50/50 on the sandbox branch", `exp:${exp.id}`, "sandbox");
  return exp;
}

export function experimentConclude(d: TenantData, ctx: Ctx, { experimentId }: { experimentId: string }) {
  humanOf(d, ctx);
  const exp = must(d.experiments.find((e) => e.id === experimentId), "Experiment");
  if (exp.status !== "running") throw new OpError("Experiment is not running", 409);
  const seed = hashString(exp.id);
  exp.variants = exp.variants.map((v, i) => ({ ...v, conversion: i === 0 ? 0.041 : 0.041 + (seed % 2 === 0 ? 0.008 : -0.004) }));
  exp.impact = exp.variants[1].conversion! > exp.variants[0].conversion! ? "positive" : "negative";
  exp.status = "concluded";
  exp.endedAt = iso(ctx.now);
  audit(d, ctx, "experiment.concluded", { type: "experiment", id: exp.id, label: exp.title }, 2, `Variant B ${((exp.variants[1].conversion! - exp.variants[0].conversion!) * 100).toFixed(1)} pts, impact ${exp.impact}`, `exp:${exp.id}`, "sandbox");
  return exp;
}

export function experimentKeep(d: TenantData, ctx: Ctx, { experimentId }: { experimentId: string }) {
  humanOf(d, ctx);
  const exp = must(d.experiments.find((e) => e.id === experimentId), "Experiment");
  if (exp.status !== "concluded") throw new OpError("Conclude the experiment first", 409);
  const branch = must(exp.branch, "Branch");
  const commits = d.commits.filter((c) => c.branch === branch);
  const cr = createChangeRequest(d, ctx, { title: `Ship experiment: ${exp.title}`, kind: "website", branch, commits, plainDiff: [`Ship variant B "${exp.variants[1].name}" on the pricing page.`, `Result: ${exp.impact} impact, conversion ${(exp.variants[0].conversion! * 100).toFixed(1)}% → ${(exp.variants[1].conversion! * 100).toFixed(1)}%.`], changeKind: "pricing_page", touches: { ...NO_TOUCH, publicContent: true, money: true, clusters: ["finebase-platform"] }, dri: "h-hcs", correlationId: `exp:${exp.id}` });
  runChecks(d, ctx, { changeRequestId: cr.id });
  exp.changeRequestId = cr.id;
  exp.learning = `${exp.variants[1].name} beat the current toggle (${exp.impact}). Clear labels and visible savings reduce friction on pricing controls.`;
  recordLearning(d, ctx, exp.loopId);
  audit(d, ctx, "experiment.kept", { type: "experiment", id: exp.id, label: exp.title }, 3, "Kept. Pricing page change sent to L1.", `exp:${exp.id}`);
  return { experiment: exp, changeRequest: cr };
}

export function experimentDiscard(d: TenantData, ctx: Ctx, { experimentId }: { experimentId: string }) {
  humanOf(d, ctx);
  const exp = must(d.experiments.find((e) => e.id === experimentId), "Experiment");
  if (!["concluded", "previewed", "running"].includes(exp.status)) throw new OpError("Nothing to discard", 409);
  exp.status = "discarded";
  exp.learning = exp.impact === "negative" ? `${exp.variants[1]?.name} did worse than the current design. Keep the current version.` : "Discarded before a result. No change shipped.";
  const b = d.branches.find((x) => x.name === exp.branch);
  if (b) b.status = "abandoned";
  recordLearning(d, ctx, exp.loopId);
  audit(d, ctx, "experiment.discarded", { type: "experiment", id: exp.id, label: exp.title }, 2, exp.learning, `exp:${exp.id}`);
  return exp;
}

function recordLearning(d: TenantData, ctx: Ctx, loopId: string) {
  const loop = d.loops.find((l) => l.id === loopId);
  const stage = loop?.stages.find((s) => s.key === "learning");
  if (stage) stage.metric.value = String(Number(stage.metric.value) + 1 || 1);
  const tpl = d.templates.find((t) => t.id === "tpl-experiments");
  const field = tpl?.fields.find((f) => f.key === "learnings");
  if (field) {
    field.value = String(Number(field.value ?? 0) + 1);
    field.filledAt = iso(ctx.now);
    field.filledBy = "a-insights";
  }
}

// ---------------------------------------------------------------- overnight improvement

export function runOvernightReview(d: TenantData, ctx: Ctx) {
  const q: Ctx = { now: ctx.now, actor: { kind: "agent", id: "a-quality", name: "Quality Supervisor" } };
  const since = ctx.now - DAY;
  const window = d.runs.filter((r) => Date.parse(r.startedAt) >= since);
  const failures = window.filter((r) => ["failed", "blocked", "escalated"].includes(r.status));
  const classes = new Map<string, number>();
  for (const r of failures) classes.set(r.failureClass ?? (r.status === "escalated" ? "needed a human" : "other"), (classes.get(r.failureClass ?? (r.status === "escalated" ? "needed a human" : "other")) ?? 0) + 1);
  const date = iso(ctx.now).slice(0, 10);
  const items: DigestItem[] = [];

  // C0: refresh a template field from a verified source. Applied automatically and logged.
  const tpl = d.templates.find((t) => t.id === "tpl-revenue-health") ?? d.templates[0];
  if (tpl) {
    const c = commit(d, q, "main", `Refresh ${tpl.name}: ${tpl.fields[0].label} from verified billing source`, [{ op: "modify", nodeType: "template", nodeId: tpl.id, label: tpl.name, field: tpl.fields[0].key, before: tpl.fields[0].value, after: tpl.fields[0].value }], 0);
    tpl.fields[0].filledAt = iso(ctx.now);
    items.push({ id: nextId(d, "dg"), kind: "auto_fix", title: `Refreshed ${tpl.name}`, detail: `${tpl.fields[0].label} refreshed from a verified source. Commit ${c.id}.`, criticality: 0, href: `/l2/versioning?commit=${c.id}`, at: iso(ctx.now) });
    audit(d, q, "fix.applied", { type: "template", id: tpl.id, label: tpl.name }, 0, "C0 fix applied automatically", `overnight:${date}`);
  }
  // C1: resolver synonym, applied by the supervisor agent with tests passing.
  const rr = d.resolver.find((r) => r.skill.id === "refund-standard") ?? d.resolver[0];
  if (rr) {
    const c = commit(d, q, "main", `Resolver: add synonym "chargeback" → ${rr.skill.id}`, [{ op: "modify", nodeType: "resolver", nodeId: rr.id, label: `Route ${rr.skill.id}`, field: "match", before: rr.match, after: `${rr.match}, chargeback` }], 1);
    rr.match = rr.match.includes("chargeback") ? rr.match : `${rr.match}, chargeback`;
    items.push({ id: nextId(d, "dg"), kind: "auto_fix", title: 'Resolver synonym "chargeback"', detail: `3 runs were misrouted yesterday. Trigger evals pass. Commit ${c.id}. Steward notified.`, criticality: 1, href: "/l2/resolver", at: iso(ctx.now) });
    audit(d, q, "fix.applied", { type: "resolver", id: rr.id, label: "Resolver synonym" }, 1, "C1 fix applied, tests passing, steward notified", `overnight:${date}`);
    notify(d, q, { to: "h-aiops", title: "C1 fix applied overnight", body: 'Resolver synonym "chargeback"', href: "/l2/resolver", kind: "digest" });
  }
  // C2 and above: drafted as change requests.
  const branch = `sandbox/overnight-${date}`;
  ensureBranch(d, q, branch, "Overnight drafts from the Quality Supervisor");
  const dunning = d.skills.find((s) => s.id === "billing-dunning");
  if (dunning) {
    const draft: Skill = { ...structuredClone(dunning), branch, status: "draft", origin: "overnight", steps: [dunning.steps[0], { id: `${dunning.id}-retry`, kind: "tool", text: "Retry the charge once before sending a reminder", tool: "tool:billing.retry" }, ...dunning.steps.slice(1, 2)] };
    d.skills.push(draft);
    const c = commit(d, q, branch, "Billing dunning: retry card once before the reminder", [{ op: "modify", nodeType: "skill", nodeId: dunning.id, label: dunning.name, field: "steps", before: "Remind, then retry after 3 days", after: "Retry once, then remind" }], 2);
    const cr = createChangeRequest(d, q, { title: "Billing dunning: retry once before the reminder", kind: "fix", branch, commits: [c], plainDiff: ["Failed payment recovery retries the card once before emailing the customer.", "Yesterday 4 customers got a reminder for a charge that would have succeeded on retry."], changeKind: "skill_step_edit", touches: NO_TOUCH, dri: "h-aiops", correlationId: `overnight:${date}` });
    runChecks(d, q, { changeRequestId: cr.id });
    items.push({ id: nextId(d, "dg"), kind: "drafted", title: cr.title, detail: `C${cr.criticality} drafted, waiting for an L2 steward.`, criticality: cr.criticality, href: `/l2/versioning/${cr.id}`, at: iso(ctx.now) });
  }
  const conflict = d.librarian.find((i) => i.id === "lib-refund-window");
  if (conflict) items.push({ id: nextId(d, "dg"), kind: "drafted", title: "Refund handling drifts from refund window v3", detail: "Observed refunds match the documented policy at 62%. The Librarian has a conflict to propose.", criticality: 3, href: "/l2/vault", at: iso(ctx.now) });
  for (const ap of d.approvals.filter((a) => a.status === "pending").slice(0, 4)) items.push({ id: nextId(d, "dg"), kind: "waiting", title: ap.title, detail: `C${ap.criticality} waiting for ${ap.requiredApprovers.count} ${ap.requiredApprovers.tier}`, criticality: ap.criticality, href: `/l1/approvals/${ap.id}`, at: ap.createdAt });
  for (const [name, count] of classes) items.push({ id: nextId(d, "dg"), kind: "failure", title: `${count} × ${name}`, detail: "Classified by the Quality Supervisor", criticality: 0, href: null, at: iso(ctx.now) });

  const digest: Digest = { date, generatedAt: iso(ctx.now), generatedBy: "Quality Supervisor", runs: window.length, failures: failures.length, failureClasses: [...classes].map(([name, count]) => ({ name, count })), items };
  d.digest = digest;
  audit(d, q, "digest.generated", { type: "digest", id: date, label: `Digest ${date}` }, 0, `${window.length} runs, ${failures.length} failures, ${items.filter((i) => i.kind === "auto_fix").length} fixes applied, ${items.filter((i) => i.kind === "drafted").length} drafted`, `overnight:${date}`);
  return digest;
}

// ---------------------------------------------------------------- studio, security, misc

export function saveSkillDraft(d: TenantData, ctx: Ctx, { skillId, trigger, steps }: { skillId: string; trigger: string; steps: { kind: Skill["steps"][number]["kind"]; text: string; tool: string | null }[] }) {
  const h = humanOf(d, ctx);
  if (h.tier === "L3") throw new OpError("Skills are authored at L2", 403);
  const live = must(d.skills.find((s) => s.id === skillId && s.branch === "main"), "Skill");
  const branch = `sandbox/edit-${skillId}-${d.counter + 1}`;
  ensureBranch(d, ctx, branch, `Edit ${live.name}`);
  const draft: Skill = { ...structuredClone(live), branch, status: "draft", trigger, steps: steps.map((s, i) => ({ ...s, id: `${skillId}-e${i}` })), updatedAt: iso(ctx.now) };
  d.skills.push(draft);
  const before = live.steps.map((s) => s.text).join(" → ");
  const after = draft.steps.map((s) => s.text).join(" → ");
  const c = commit(d, ctx, branch, `Edit ${live.name}`, [{ op: "modify", nodeType: "skill", nodeId: skillId, label: live.name, field: "steps", before, after }], 2);
  const touchesMoney = live.tools.some((t) => t.includes("billing"));
  return createChangeRequest(d, ctx, { title: `Edit skill: ${live.name}`, kind: "skill", branch, commits: [c], plainDiff: [`${live.name}: steps change.`, trigger !== live.trigger ? `Trigger changes to "${trigger}".` : "Trigger unchanged."], changeKind: "skill_step_edit", touches: { ...NO_TOUCH, money: touchesMoney, clusters: [live.clusterId] }, dri: live.dri, correlationId: `skill:${skillId}` });
}

export function promoteAgent(d: TenantData, ctx: Ctx, { agentId }: { agentId: string }) {
  const h = humanOf(d, ctx);
  if (h.tier === "L3") throw new OpError("Promotions are proposed at L2", 403);
  const agent = must(d.agents.find((a) => a.id === agentId), "Agent");
  const next = agent.autonomy === "trainee" ? "supervised" : agent.autonomy === "supervised" ? "autonomous" : null;
  if (!next) throw new OpError("Already autonomous", 409);
  const branch = `sandbox/promote-${agent.id}-${d.counter + 1}`;
  ensureBranch(d, ctx, branch, `Promote ${agent.name}`);
  const c = commit(d, ctx, branch, `Promote ${agent.name} to ${next}`, [{ op: "modify", nodeType: "agent", nodeId: agent.id, label: agent.name, field: "autonomy", before: agent.autonomy, after: next }], next === "autonomous" ? 3 : 2);
  const cr = createChangeRequest(d, ctx, { title: `Promote ${agent.name} to ${next}`, kind: "security", branch, commits: [c], plainDiff: [`${agent.name} moves from ${agent.autonomy} to ${next}.`, `Task success ${Math.round(agent.taskSuccess * 100)}%.`], changeKind: next === "autonomous" ? "new_policy" : "skill_step_edit", touches: NO_TOUCH, dri: agent.dri, correlationId: `agent:${agent.id}` });
  runChecks(d, ctx, { changeRequestId: cr.id });
  return cr;
}

const REVEAL_NAMES = ["Kavindi Perera", "Sahan Madushanka", "Ravindu Nanayakkara", "Dinusha Peiris", "Prasanna Alwis"];
export function revealPersonal(d: TenantData, ctx: Ctx, { targetId, field }: { targetId: string; field: string }) {
  const h = humanOf(d, ctx);
  const clearance = h.attributes.clearance;
  if (!["confidential", "restricted"].includes(clearance)) throw new OpError("Revealing personal data needs confidential clearance", 403);
  audit(d, ctx, "pii.revealed", { type: "conversation", id: targetId, label: field }, 2, `${h.name} revealed ${field}`, null);
  return { value: REVEAL_NAMES[hashString(targetId) % REVEAL_NAMES.length], revealedAt: iso(ctx.now) };
}

export function addTrackingItem(d: TenantData, ctx: Ctx, item: { selector: string; elementLabel: string; eventName: string; properties: string[]; personalData: boolean; maskText: boolean; subscribers: string[] }) {
  const h = humanOf(d, ctx);
  if (!/^[a-z0-9_.]+$/.test(item.eventName)) throw new OpError("Event names use lowercase letters, digits, dots and underscores");
  const tp = { id: nextId(d, "tp"), selector: item.selector, elementLabel: item.elementLabel, eventName: item.eventName, properties: item.properties, privacy: { personalData: item.personalData, maskText: item.maskText }, subscribers: item.subscribers, createdBy: h.id, createdAt: iso(ctx.now) };
  d.trackingPlan.unshift(tp);
  audit(d, ctx, "tracking_plan.added", { type: "tracking_plan", id: tp.id, label: tp.eventName }, 1, `Planted on ${item.elementLabel}`, null);
  return tp;
}

export function markRead(d: TenantData, _ctx: Ctx, { id }: { id: string | "all" }) {
  for (const n of d.notifications) if (id === "all" || n.id === id) n.read = true;
  return { ok: true };
}

const READS: Record<string, string[]> = { L1: ["public", "internal", "confidential", "restricted"], L2: ["public", "internal", "confidential", "restricted"], L3: ["public", "internal", "confidential"] };

/** The same rules S7 applies, run on a made-up action. Nothing changes. */
export function accessCheck(d: TenantData, _ctx: Ctx, a: { agentId: string; action: string; sensitivity: string; onBehalfOf?: string }) {
  const agent = must(d.agents.find((x) => x.id === a.agentId), "Agent");
  const person = a.onBehalfOf ? must(d.humans.find((h) => h.id === a.onBehalfOf), "Person") : null;
  const effective = person && person.tier > agent.tier ? person.tier : agent.tier;  // "L3" > "L1": the lower tier wins
  const base = { tier: agent.tier, effectiveTier: effective };
  if (a.action !== "escalate" && !agent.capabilities.includes(a.action)) return { ...base, allow: false, ruleId: "missing_capability", reason: "principal lacks this capability" };
  if (!READS[agent.tier].includes(a.sensitivity)) return { ...base, allow: false, ruleId: "sensitivity_by_tier", reason: "data too sensitive for this tier" };
  if (person && !READS[person.tier].includes(a.sensitivity)) return { ...base, allow: false, ruleId: "on_behalf_of", reason: "the person acted for may not see this data" };
  return { ...base, allow: true, ruleId: "capability_and_tier", reason: "capability held and data readable" };
}

export const OPS = {
  takeover, handback, markRunWrong, sendMessage, closeConversation, skillify, runChecks, decide, rollback, runReadinessScheduler, uploadEvidence, requestGrant, revokeGrant,
  librarianPropose, experimentPreview, experimentStart, experimentConclude, experimentKeep, experimentDiscard, runOvernightReview, saveSkillDraft, promoteAgent,
  revealPersonal, addTrackingItem, markRead, studioApply, studioSuggest, markTrendKnown, accessCheck,
} as const;
export type OpName = keyof typeof OPS;
