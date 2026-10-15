// Workflow Studio engine: builds proposals, runs the Edit Review Agent, decides who may confirm, and applies changes.
// Pure functions over one tenant's data, like the other mock operations, so journal replay stays deterministic.
import type {
  Criticality,
  FieldChange,
  FieldValue,
  Finding,
  Human,
  ItemFields,
  MemberKind,
  Proposal,
  ProposalInput,
  Review,
  Snapshot,
  StudioItem,
  StudioKind,
  Suggestion,
  Workflow,
  WorkflowDetail,
  WorkflowSummary,
} from "@/contracts";
import { approverFor } from "@/lib/governance/criticality";
import { FIELD_SPECS, KIND_LABEL, MEMBER_ORDER, TOOL_LEVEL_LABEL, describeCron, fieldLabel, formatValue, isParam, refsOf, validCron } from "@/lib/studio/spec";
import { iso } from "../prng";
import type { StudioData, TenantData } from "../types";

export const REVIEWER = "Edit Review Agent";

export class StudioError extends Error {
  status: number;
  constructor(message: string, status = 400) {
    super(message);
    this.status = status;
  }
}

type Target = StudioItem | Workflow;
const isWorkflow = (t: Target): t is Workflow => "members" in t;

// ---------------------------------------------------------------- lookups

export function workflowOf(s: StudioData, id: string | null | undefined) {
  return s.workflows.find((w) => w.id === id) ?? null;
}

export function itemOf(s: StudioData, id: string | null | undefined) {
  return s.items.find((i) => i.id === id) ?? null;
}

/** A workflow's own members, in diagram order. */
export function membersOf(s: StudioData, wf: Workflow): StudioItem[] {
  const set = new Set(wf.members);
  return s.items.filter((i) => set.has(i.id)).sort((a, b) => MEMBER_ORDER.indexOf(a.kind) - MEMBER_ORDER.indexOf(b.kind) || a.name.localeCompare(b.name));
}

export function toolIdsUsedBy(s: StudioData, wf: Workflow): string[] {
  const out = new Set<string>();
  for (const m of membersOf(s, wf)) for (const r of refsOf(m.kind, m.fields)) if (r.ref === "tool") out.add(r.id);
  return [...out];
}

/** Members plus the shared tools the workflow uses. */
export function scopeOf(s: StudioData, wf: Workflow): StudioItem[] {
  const tools = toolIdsUsedBy(s, wf).map((id) => itemOf(s, id)).filter((x): x is StudioItem => !!x);
  return [...membersOf(s, wf), ...tools];
}

export function workflowsUsingTool(s: StudioData, toolId: string): Workflow[] {
  return s.workflows.filter((w) => toolIdsUsedBy(s, w).includes(toolId));
}

/** Items that point at `id`. For tools this spans every workflow, since tools are shared. */
function referrers(s: StudioData, id: string, wf: Workflow | null): { item: StudioItem; rel: string; key: string }[] {
  const pool = wf && !id.startsWith("tool:") ? membersOf(s, wf) : s.items;
  const out: { item: StudioItem; rel: string; key: string }[] = [];
  for (const it of pool) for (const r of refsOf(it.kind, it.fields)) if (r.id === id) out.push({ item: it, rel: r.rel, key: r.key });
  return out;
}

export function nameOf(s: StudioData, id: string) {
  return itemOf(s, id)?.name ?? workflowOf(s, id)?.name ?? id;
}

// ---------------------------------------------------------------- drafting

function slug(v: string) {
  return v.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 32) || "item";
}

function defaultFields(kind: MemberKind): ItemFields {
  const f: ItemFields = {};
  for (const spec of FIELD_SPECS[kind]) {
    if (spec.type === "refs" || spec.type === "list") f[spec.key] = [];
    else if (spec.type === "boolean") f[spec.key] = spec.key === "enabled";
    else if (spec.type === "number") f[spec.key] = spec.key === "rateLimitPerMin" ? 60 : spec.key === "maxConcurrent" ? 2 : spec.key === "retentionDays" ? 365 : 0;
    else if (spec.type === "select") f[spec.key] = spec.options?.[0] ?? "";
    else f[spec.key] = "";
  }
  if (kind === "scheduler") f.timezone = "Asia/Colombo";
  if (kind === "agent") f.model = "claude-sonnet-5-5";
  if (kind === "policy") f.criticality = "3";
  return f;
}

function snapshotOf(t: Target): Snapshot {
  return isWorkflow(t)
    ? { name: t.name, description: t.description, topics: [...t.topics], status: t.status, fields: { criticality: String(t.criticality), dri: t.dri } }
    : { name: t.name, description: t.description, topics: [...t.topics], status: t.status, fields: structuredClone(t.fields) };
}

function eq(a: FieldValue | undefined, b: FieldValue | undefined) {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
}

/** Before and after states of the target for an input, without touching the store. */
function materialize(d: TenantData, h: Human, input: ProposalInput): { before: Target | null; after: Target | null; wf: Workflow | null } {
  const s = d.studio;
  const p = input.patch;
  if (input.kind === "workflow") {
    const before = input.intent === "create" ? null : workflowOf(s, input.targetId);
    if (input.intent !== "create" && !before) throw new StudioError("Workflow not found", 404);
    if (input.intent === "delete") return { before, after: null, wf: before };
    const base: Workflow = before
      ? structuredClone(before)
      : { id: `wf-${slug(p.name ?? "new-workflow")}`, tenantId: d.tenant.id, name: p.name ?? "New workflow", description: "", topics: [], status: "draft", version: 0, clusterId: d.clusters[0]?.id ?? "", dri: h.id, editors: [], criticality: 2, members: [], story: null, updatedAt: "", updatedBy: h.id };
    const after: Workflow = { ...base, ...(p.story && { story: p.story }), ...(p.name !== undefined && { name: p.name }), ...(p.description !== undefined && { description: p.description }), ...(p.topics && { topics: p.topics }), ...(p.status && { status: p.status }), ...(p.dri && { dri: p.dri }) };
    if (p.fields?.criticality !== undefined) after.criticality = Math.max(0, Math.min(4, Number(p.fields.criticality))) as Criticality;
    return { before, after, wf: before ?? after };
  }
  const before = input.intent === "create" ? null : itemOf(s, input.targetId);
  if (input.intent !== "create" && !before) throw new StudioError(`${KIND_LABEL[input.kind]} not found`, 404);
  const wfId = input.kind === "tool" ? null : before?.workflowId ?? input.workflowId;
  const wf = workflowOf(s, wfId ?? input.workflowId);
  if (input.kind !== "tool" && !wf) throw new StudioError("Pick a workflow first", 400);
  if (input.intent === "delete") return { before, after: null, wf };
  const kind = input.kind as MemberKind;
  const name = p.name ?? before?.name ?? `New ${KIND_LABEL[kind].toLowerCase()}`;
  const base: StudioItem = before
    ? structuredClone(before)
    : {
        id: kind === "tool" ? `tool:${slug(name).replace(/-/g, ".")}` : `${wf!.id.replace(/^wf-/, "")}.${kind}.${slug(name)}-${(d.counter + 1).toString(36)}`,
        kind, workflowId: kind === "tool" ? null : wf!.id, name, description: "", topics: [], status: "active", version: 0, dri: wf?.dri ?? h.id, fields: defaultFields(kind), updatedAt: "", updatedBy: h.id,
      };
  const after: StudioItem = {
    ...base,
    ...(p.name !== undefined && { name: p.name }),
    ...(p.description !== undefined && { description: p.description }),
    ...(p.topics && { topics: p.topics }),
    ...(p.status && { status: p.status }),
    ...(p.dri && { dri: p.dri }),
    fields: { ...base.fields, ...(p.fields ?? {}) },
  };
  return { before, after, wf };
}

function diff(s: StudioData, kind: StudioKind, before: Target | null, after: Target | null): FieldChange[] {
  if (before && !after) return [{ field: "_delete", label: KIND_LABEL[kind], before: before.name, after: "deleted" }];
  const b = before ? snapshotOf(before) : null;
  const a = after ? snapshotOf(after) : null;
  const out: FieldChange[] = [];
  const isRef = (key: string) => kind !== "workflow" && FIELD_SPECS[kind].some((f) => f.key === key && (f.type === "refs" || f.type === "ref"));
  const show = (v: FieldValue | undefined, key: string) => {
    if (v === undefined || (Array.isArray(v) && v.length === 0) || v === "") return null;
    if (isRef(key)) return (Array.isArray(v) ? v : [String(v)]).map((id) => nameOf(s, id)).join(", ");
    if (key === "cron") return `${describeCron(String(v))} (${v})`;
    if (kind === "tool" && key === "level") return TOOL_LEVEL_LABEL[String(v)] ?? String(v);
    // Code is read in the editor, not in a diff line.
    if (kind === "tool" && key === "code") return `${String(v).trim().split("\n").length} lines`;
    return formatValue(v, key);
  };
  for (const key of ["name", "description", "topics", "status"] as const) {
    if (!eq(b?.[key], a?.[key])) out.push({ field: key, label: fieldLabel(kind, key), before: show(b?.[key], key), after: show(a?.[key], key) });
  }
  const keys = new Set([...Object.keys(b?.fields ?? {}), ...Object.keys(a?.fields ?? {})]);
  for (const key of keys) {
    if (!eq(b?.fields[key], a?.fields[key])) out.push({ field: key, label: fieldLabel(kind, key), before: show(b?.fields[key], key), after: show(a?.fields[key], key) });
  }
  if (before && after && "dri" in before && before.dri !== after.dri) out.push({ field: "dri", label: "DRI", before: before.dri, after: after.dri });
  if ((before && isWorkflow(before)) || (after && isWorkflow(after))) {
    const count = (t: Target | null) => (t && isWorkflow(t) && t.story ? `${t.story.scenarios.length} scenario${t.story.scenarios.length === 1 ? "" : "s"}` : null);
    const sb = before && isWorkflow(before) ? before.story : null;
    const sa = after && isWorkflow(after) ? after.story : null;
    if (sa && sb?.problem !== sa.problem) out.push({ field: "story.problem", label: "Problem", before: sb?.problem ?? null, after: sa.problem });
    if (JSON.stringify(sb?.scenarios ?? []) !== JSON.stringify(sa?.scenarios ?? [])) out.push({ field: "story.scenarios", label: "Scenarios", before: count(before), after: count(after) });
  }
  return out.filter((c) => c.before !== c.after);
}

// ---------------------------------------------------------------- the Edit Review Agent

type Ctx2 = { s: StudioData; d: TenantData; wf: Workflow | null };

function fix(label: string, input: ProposalInput): Suggestion {
  return { label, prompt: label, tone: "fix", input };
}

function removeRef(item: StudioItem, key: string, id: string): ProposalInput {
  const v = item.fields[key];
  const next = Array.isArray(v) ? v.filter((x) => x !== id) : "";
  return { intent: "update", kind: item.kind, targetId: item.id, workflowId: item.workflowId, patch: { fields: { [key]: next } } };
}

function addToList(item: StudioItem, key: string, value: string): ProposalInput {
  const v = item.fields[key];
  const list = Array.isArray(v) ? v : [];
  return { intent: "update", kind: item.kind, targetId: item.id, workflowId: item.workflowId, patch: { fields: { [key]: [...new Set([...list, value])] } } };
}

/** Problems in the state an item would be in. Used both for a change and for the workflow health check. */
function itemFindings(c: Ctx2, it: StudioItem, scope: StudioItem[]): { findings: Finding[]; fixes: Suggestion[] } {
  const findings: Finding[] = [];
  const fixes: Suggestion[] = [];
  const inScope = new Map(scope.map((x) => [x.id, x]));
  const ref = { kind: it.kind, id: it.id } as const;
  if (it.status === "retired") return { findings, fixes };
  for (const r of refsOf(it.kind, it.fields)) {
    const target = inScope.get(r.id) ?? itemOf(c.s, r.id);
    if (!target) {
      findings.push({ severity: "break", text: `${it.name} ${r.rel} an item that no longer exists (${r.id}).`, ref });
      fixes.push(fix(`Remove the missing link from ${it.name}`, removeRef(it, r.key, r.id)));
    } else if (r.ref !== "tool" && target.workflowId !== it.workflowId) {
      findings.push({ severity: "break", text: `${it.name} ${r.rel} ${target.name}, which belongs to another workflow. Only tools are shared.`, ref });
      fixes.push(fix(`Remove ${target.name} from ${it.name}`, removeRef(it, r.key, r.id)));
    } else if (target.status === "retired" || target.status === "paused") {
      findings.push({ severity: r.ref === "tool" || r.ref === "agent" ? "break" : "warn", text: `${it.name} ${r.rel} ${target.name}, which is ${target.status}.`, ref });
      fixes.push(fix(`Resume ${target.name}`, { intent: "update", kind: target.kind, targetId: target.id, workflowId: target.workflowId, patch: { status: "active" } }));
    }
  }
  if (it.kind === "skill") {
    const agents = ((it.fields.agents as string[]) ?? []).map((id) => inScope.get(id)).filter((a): a is StudioItem => !!a && a.status === "active");
    if (agents.length === 0 && it.status === "active") {
      findings.push({ severity: "break", text: `No active agent runs ${it.name}, so it will never execute.`, ref });
      const candidate = scope.find((x) => x.kind === "agent" && x.status === "active");
      if (candidate) fixes.push(fix(`Assign ${candidate.name} to ${it.name}`, addToList(it, "agents", candidate.id)));
    }
    const tools = (it.fields.tools as string[]) ?? [];
    for (const step of (it.fields.steps as string[]) ?? []) {
      const m = step.match(/\[(tool:[^\]]+)\]/);
      if (m && !tools.includes(m[1])) {
        findings.push({ severity: "break", text: `Step "${step.replace(/\s*\[.*\]$/, "")}" calls ${m[1].replace("tool:", "")}, but ${it.name} does not list that tool.`, ref });
        fixes.push(fix(`Add ${m[1].replace("tool:", "")} to ${it.name}`, addToList(it, "tools", m[1])));
      }
    }
    for (const toolId of tools) {
      const tool = itemOf(c.s, toolId);
      const cap = tool ? String(tool.fields.capability ?? "") : "";
      if (!cap) continue;
      for (const a of agents) {
        const caps = (a.fields.capabilities as string[]) ?? [];
        if (!caps.includes(cap)) {
          findings.push({ severity: "break", text: `${a.name} runs ${it.name} but lacks ${cap}, which ${tool!.name} needs. Calls will be denied.`, ref: { kind: "agent", id: a.id } });
          fixes.push(fix(`Grant ${cap} to ${a.name}`, addToList(a, "capabilities", cap)));
        }
      }
    }
    if (((it.fields.policies as string[]) ?? []).length === 0) findings.push({ severity: "warn", text: `${it.name} has no governing policy. Nothing limits what it may do.`, ref });
    if (Number(it.fields.evalCases ?? 0) < 10) findings.push({ severity: "warn", text: `${it.name} has ${Number(it.fields.evalCases ?? 0)} eval cases. Ten or more make a change safe to judge.`, ref });
  }
  if (it.kind === "scheduler") {
    const cron = String(it.fields.cron ?? "");
    if (!validCron(cron)) findings.push({ severity: "break", text: `${it.name} has an invalid cron "${cron}". It will never fire.`, ref });
    if (!it.fields.target) findings.push({ severity: "break", text: `${it.name} does not say which skill to run.`, ref });
    if (it.fields.enabled === false) findings.push({ severity: "warn", text: `${it.name} is turned off. ${nameOf(c.s, String(it.fields.target))} will not run on schedule.`, ref });
  }
  if (it.kind === "sensor") {
    if (it.fields.health === "down") findings.push({ severity: "warn", text: `${it.name} is down. Skills reading it work on stale data.`, ref });
    if (it.fields.health === "degraded") findings.push({ severity: "info", text: `${it.name} is degraded.`, ref });
  }
  if (it.kind === "agent" && it.status === "active") {
    const runs = scope.some((x) => x.kind === "skill" && x.status === "active" && ((x.fields.agents as string[]) ?? []).includes(it.id));
    if (!runs) findings.push({ severity: "warn", text: `${it.name} runs no skill in this workflow.`, ref });
  }
  if (it.kind === "template" && it.status === "active") {
    const filled = scope.some((x) => x.kind === "skill" && ((x.fields.templates as string[]) ?? []).includes(it.id));
    const learned = scope.some((x) => x.kind === "loop" && x.fields.learning === it.id);
    if (!filled && !learned) findings.push({ severity: "warn", text: `No skill fills ${it.name}, so it will go stale.`, ref });
  }
  if (it.kind === "tool" && it.fields.level === "custom") {
    const test = sandboxTest(String(it.fields.code ?? ""));
    findings.push(test.ok ? { severity: "info", text: `${it.name} passed its sandbox test run.`, ref } : { severity: "break", text: `${it.name} failed its sandbox test run: ${test.reason}`, ref });
  }
  if (it.kind === "policy" && it.status === "active") {
    const governs = scope.some((x) => (x.kind === "skill" && ((x.fields.policies as string[]) ?? []).includes(it.id)) || (x.kind === "loop" && ((x.fields.guards as string[]) ?? []).includes(it.id)));
    if (!governs) findings.push({ severity: "info", text: `${it.name} does not govern any skill yet.`, ref });
  }
  return { findings, fixes };
}

/** Mock sandbox run for a custom tool. A real backend executes the code in isolation; this checks the same contract. */
export function sandboxTest(code: string): { ok: true } | { ok: false; reason: string } {
  if (!code.trim()) return { ok: false, reason: "there is no code yet." };
  if (!/export\s+async\s+function\s+run\s*\(/.test(code)) return { ok: false, reason: "it needs an exported async run(input) function." };
  const reach = code.match(/process\.env|child_process|require\(|\beval\(|new Function/);
  if (reach) return { ok: false, reason: `it reaches outside the sandbox (${reach[0]}).` };
  let depth = 0;
  for (const ch of code) {
    depth += ch === "{" ? 1 : ch === "}" ? -1 : 0;
    if (depth < 0) break;
  }
  if (depth !== 0) return { ok: false, reason: "its braces do not balance." };
  return { ok: true };
}

export function healthOf(d: TenantData, wf: Workflow) {
  const scope = scopeOf(d.studio, wf);
  const c: Ctx2 = { s: d.studio, d, wf };
  const findings: Finding[] = [];
  const fixes: Suggestion[] = [];
  // Shared tools are checked too, so a custom tool that fails its sandbox test shows up where it is used.
  for (const it of scope) {
    const r = itemFindings(c, it, scope);
    findings.push(...r.findings);
    fixes.push(...r.fixes);
  }
  const seen = new Set<string>();
  return { findings, fixes: fixes.filter((f) => (seen.has(f.label) ? false : (seen.add(f.label), true))) };
}

function touchesFor(s: StudioData, kind: StudioKind, after: Target | null, before: Target | null, changes: FieldChange[]) {
  const it = (after ?? before) as StudioItem | Workflow | null;
  const t = { money: false, public: false, personal: false };
  if (!it || isWorkflow(it)) return t;
  const tools = it.kind === "tool" ? [it] : refsOf(it.kind, it.fields).filter((r) => r.ref === "tool").map((r) => itemOf(s, r.id)).filter((x): x is StudioItem => !!x);
  if (tools.some((x) => x.fields.sideEffect === "money")) t.money = true;
  if (tools.some((x) => x.fields.sideEffect === "public")) t.public = true;
  if (kind === "policy" && changes.some((c) => /amount|Minor/i.test(c.field))) t.money = true;
  if (kind === "sensor" && (it.fields.personalData === true || changes.some((c) => c.field === "retentionDays" || c.field === "personalData"))) t.personal = true;
  if (changes.some((c) => FIELD_SPECS[it.kind]?.find((f) => f.key === c.field)?.sensitive === "personal")) t.personal = true;
  return t;
}

function baseLevel(input: ProposalInput, changes: FieldChange[], before: Target | null, after: Target | null): { level: Criticality; reason: string } {
  const fields = changes.map((c) => c.field);
  const metaOnly = fields.every((f) => ["name", "description", "topics"].includes(f));
  if (input.intent === "update" && fields.length > 0 && fields.every((f) => f === "topics")) return { level: 0, reason: "a topic change starts at C0" };
  if (input.intent === "update" && metaOnly) return { level: 1, reason: "a wording change starts at C1" };
  const k = input.kind;
  if (k === "workflow") return input.intent === "update" && !fields.includes("status") ? { level: 1, reason: "a workflow setting change starts at C1" } : { level: input.intent === "create" ? 2 : 3, reason: `${input.intent === "create" ? "a new workflow starts at C2" : "pausing, retiring or deleting a workflow starts at C3"}` };
  const custom = (after as StudioItem | null)?.fields?.level === "custom";
  if (k === "tool" && custom && input.intent !== "delete" && (input.intent === "create" || fields.includes("code") || fields.includes("level"))) return { level: 3, reason: "custom tool code starts at C3, so a person approves it once before agents call it" };
  if (k === "tool") return input.intent === "create" ? { level: 2, reason: "a new shared tool starts at C2" } : { level: 3, reason: "a shared tool change starts at C3, since other workflows depend on it" };
  if (k === "policy") return { level: 3, reason: `a policy ${input.intent === "update" ? "change" : input.intent === "create" ? "addition" : "removal"} starts at C3` };
  if (k === "skill") return input.intent === "update" ? { level: 2, reason: "a skill edit starts at C2" } : { level: 3, reason: `a skill ${input.intent === "create" ? "addition" : "removal"} starts at C3` };
  if (k === "agent") {
    const b = before as StudioItem | null;
    const a = after as StudioItem | null;
    const addedCaps = ((a?.fields.capabilities as string[]) ?? []).filter((x) => !((b?.fields.capabilities as string[]) ?? []).includes(x));
    if (addedCaps.length) return { level: 4, reason: `granting ${addedCaps.join(", ")} is a capability grant, C4` };
    if (a?.fields.autonomy === "autonomous" && b?.fields.autonomy !== "autonomous") return { level: 3, reason: "making an agent autonomous starts at C3" };
    return { level: 2, reason: `an agent ${input.intent === "update" ? "change" : input.intent === "create" ? "addition" : "removal"} starts at C2` };
  }
  if (k === "sensor") return { level: 2, reason: "a data scope change starts at C2" };
  if (k === "loop") return { level: 2, reason: "a loop change starts at C2" };
  if (k === "scheduler") return fields.includes("enabled") || input.intent === "delete" ? { level: 2, reason: "stopping or removing a schedule starts at C2" } : { level: 1, reason: "a timing change starts at C1" };
  return { level: 1, reason: "a template change starts at C1" };
}

function authorityFor(h: Human, wf: Workflow | null, level: Criticality, verdict: Review["verdict"]): Review["authority"] {
  if (h.tier === "L3") return { canApply: false, route: "view_only", approver: wf ? `the workflow DRI` : "an L2 steward", reason: "L3 can view workflows and suggest edits, but cannot change them." };
  const req = approverFor(level);
  // L2 stewards draft changes and send them for approval. They never apply a change themselves.
  if (h.tier === "L2") return { canApply: false, route: "approval", approver: approverFor(Math.max(level, 2) as Criticality).label, reason: "L2 drafts changes and sends them for approval. It cannot apply a change itself." };
  const owns = !!wf && (wf.dri === h.id || wf.editors.includes(h.id));
  const okLevel = level <= h.maxApprovalCriticality;
  if (verdict !== "breaking" && level <= 1) return { canApply: true, route: "apply", approver: "you", reason: `C${level} is logged and applied right away.` };
  if (verdict !== "breaking" && level === 2 && (owns || h.tier === "L1") && okLevel) return { canApply: true, route: "apply", approver: "you", reason: `You ${owns ? "own this workflow" : "are L1"} and C2 is inside your approval ceiling.` };
  const why = verdict === "breaking" ? "The Edit Review Agent marked this breaking, so a second person must look." : level >= 3 ? `C${level} needs ${req.label}, and nobody approves their own change.` : !owns ? "Only the workflow DRI or its editors confirm C2 edits." : `C${level} is above your ceiling of C${h.maxApprovalCriticality}.`;
  return { canApply: false, route: "approval", approver: verdict === "breaking" && level < 2 ? approverFor(2).label : req.label, reason: why };
}

export function review(d: TenantData, h: Human, input: ProposalInput): Proposal {
  const s = d.studio;
  const { before, after, wf } = materialize(d, h, input);
  const changes = diff(s, input.kind, before, after);
  if (input.intent === "update" && changes.length === 0) throw new StudioError("Nothing would change. Say what the new value should be.", 422);
  const target = (after ?? before)!;
  const targetName = target.name;
  const findings: Finding[] = [];
  const fixes: Suggestion[] = [];
  const affected: Review["affected"] = [];
  const otherWorkflows: Review["otherWorkflows"] = [];
  const c: Ctx2 = { s, d, wf };
  const addAffected = (it: StudioItem | Workflow, how: string) => {
    if (affected.some((a) => a.id === it.id)) return;
    affected.push({ kind: isWorkflow(it) ? "workflow" : it.kind, id: it.id, name: it.name, workflowId: isWorkflow(it) ? it.id : it.workflowId, how });
  };
  addAffected(target, input.intent === "create" ? "created" : input.intent === "delete" ? "deleted" : "changed");

  if (isWorkflow(target)) {
    const members = membersOf(s, target);
    if (input.intent === "delete" && members.length) findings.push({ severity: "break", text: `Deleting ${target.name} removes its ${members.length} members. Shared tools stay.`, ref: null });
    if (after && (after as Workflow).status !== "active" && before && (before as Workflow).status === "active") findings.push({ severity: "warn", text: `Every skill in ${target.name} stops taking work while it is ${(after as Workflow).status}.`, ref: null });
    for (const m of members.slice(0, 12)) if (input.intent === "delete" || changes.some((x) => x.field === "status")) addAffected(m, input.intent === "delete" ? "deleted with the workflow" : "stops with the workflow");
  } else {
    const item = target as StudioItem;
    const inbound = referrers(s, item.id, wf);
    for (const r of inbound) addAffected(r.item, `${r.rel} ${item.name}`);
    for (const r of refsOf(item.kind, item.fields)) {
      const t = itemOf(s, r.id);
      if (t) addAffected(t, `${item.name} ${r.rel} it`);
    }
    if (item.kind === "tool") {
      for (const w of workflowsUsingTool(s, item.id)) if (w.id !== wf?.id) otherWorkflows.push({ id: w.id, name: w.name, via: `uses ${item.name}` });
    }
    if (input.intent === "delete") {
      for (const r of inbound) {
        const sev = r.item.status === "retired" ? "info" : "break";
        findings.push({ severity: sev, text: `${r.item.name} ${r.rel} ${item.name}. After the delete it points at nothing.`, ref: { kind: r.item.kind, id: r.item.id } });
        fixes.push(fix(`Remove ${item.name} from ${r.item.name} first`, removeRef(r.item, r.key, item.id)));
      }
      if (!inbound.length) findings.push({ severity: "info", text: `Nothing else in the workflow points at ${item.name}.`, ref: null });
    } else {
      const scope = wf ? scopeOf(s, wf).map((x) => (x.id === item.id ? item : x)) : [item];
      if (input.intent === "create" && wf && item.kind !== "tool") scope.push(item);
      const own = itemFindings(c, item, scope);
      const prev = before ? itemFindings(c, before as StudioItem, wf ? scopeOf(s, wf) : [before as StudioItem]) : { findings: [], fixes: [] };
      const known = new Set(prev.findings.map((f) => f.text));
      // Problems that existed before this change are shown, but they do not count against it.
      for (const f of own.findings) findings.push(known.has(f.text) ? { ...f, severity: "info", text: `Already true before this change: ${f.text}` } : f);
      fixes.push(...own.fixes);
      // Items that depend on this one may break because of it, in this workflow or, for a shared tool, in others.
      for (const r of inbound) {
        const home = workflowOf(s, r.item.workflowId);
        const was = home ? scopeOf(s, home) : [r.item];
        const now = was.map((x) => (x.id === item.id ? item : x));
        const before2 = new Set(itemFindings(c, r.item, was).findings.map((f) => f.text));
        for (const f of itemFindings(c, r.item, now).findings) if (f.severity === "break" && !before2.has(f.text) && !findings.some((g) => g.text === f.text)) findings.push(f);
      }
      if (item.status !== "active" && before && (before as StudioItem).status === "active") {
        for (const r of inbound) if (r.item.status === "active") findings.push({ severity: item.kind === "tool" || item.kind === "agent" ? "break" : "warn", text: `${r.item.name} ${r.rel} ${item.name}, which becomes ${item.status}.`, ref: { kind: r.item.kind, id: r.item.id } });
      }
      for (const ch of changes) {
        if (item.kind === "policy" && isParam(ch.field)) {
          const b = Number((before as StudioItem | null)?.fields[ch.field]);
          const a = Number(item.fields[ch.field]);
          if (Number.isFinite(a) && Number.isFinite(b) && a !== b) {
            const looser = a > b;
            findings.push({ severity: "warn", text: looser ? `${ch.label} goes from ${ch.before} to ${ch.after}. More cases are handled without a person.` : `${ch.label} goes from ${ch.before} to ${ch.after}. More cases will escalate to people.`, ref: null });
          }
        }
        const spec = FIELD_SPECS[item.kind].find((f) => f.key === ch.field);
        if (spec && (spec.type === "refs" || spec.type === "ref") && before) {
          const ids = (v: FieldValue | undefined) => (Array.isArray(v) ? v : typeof v === "string" && v ? [v] : []);
          const was = ids((before as StudioItem).fields[ch.field]);
          const now = ids(item.fields[ch.field]);
          for (const id of was.filter((x) => !now.includes(x))) {
            const gone = itemOf(s, id);
            if (spec.ref === "policy") findings.push({ severity: "warn", text: `${item.name} will no longer be governed by ${gone?.name ?? id}. Check that another policy still limits it.`, ref: { kind: "policy", id } });
            else if (spec.ref === "agent") findings.push({ severity: "warn", text: `${gone?.name ?? id} stops ${spec.key === "feeds" ? "receiving events from" : "running"} ${item.name}.`, ref: { kind: "agent", id } });
            else if (spec.ref === "sensor") findings.push({ severity: "info", text: `${item.name} stops reading ${gone?.name ?? id}.`, ref: { kind: "sensor", id } });
          }
          for (const id of now.filter((x) => !was.includes(x))) {
            const added = itemOf(s, id);
            if (added && spec.ref === "tool" && (added.fields.sideEffect === "money" || added.fields.sideEffect === "public")) findings.push({ severity: "warn", text: `${item.name} gains ${added.name}, which ${added.fields.sideEffect === "money" ? "moves money" : "publishes in public"}.`, ref: { kind: "tool", id } });
          }
        }
        if (item.kind === "policy" && ch.field === "statement") findings.push({ severity: "warn", text: "The statement is what agents read. Skills governed by it will reason from the new wording.", ref: null });
        if (item.kind === "agent" && ch.field === "autonomy") findings.push({ severity: ch.after === "autonomous" ? "warn" : "info", text: ch.after === "autonomous" ? `${item.name} will act without supervision.` : `${item.name} will have more of its work checked by people.`, ref: null });
        if (item.kind === "template" && ch.field === "fieldList") {
          const removed = (((before as StudioItem | null)?.fields.fieldList as string[]) ?? []).filter((x) => !((item.fields.fieldList as string[]) ?? []).includes(x));
          if (removed.length && inbound.length) findings.push({ severity: "warn", text: `${removed.join(", ")} will stop being reported. ${inbound.map((r) => r.item.name).join(", ")} fill this template.`, ref: null });
        }
        if (item.kind === "tool" && input.intent === "update" && ch.field === "sideEffect" && (ch.after === "money" || ch.after === "public")) findings.push({ severity: "break", text: `${item.name} would start ${ch.after === "money" ? "moving money" : "publishing in public"}. Every skill that uses it needs a fresh review.`, ref: null });
        if (item.kind === "tool" && input.intent === "update" && ch.field === "capability") findings.push({ severity: "break", text: `Agents holding the old capability lose access to ${item.name} until they are granted the new one.`, ref: null });
      }
      if (item.kind === "tool" && otherWorkflows.length && input.intent === "update") findings.push({ severity: "warn", text: `${item.name} is shared. ${otherWorkflows.length} other workflow${otherWorkflows.length > 1 ? "s" : ""} change with it: ${otherWorkflows.map((w) => w.name).join(", ")}.`, ref: null });
      if (item.kind === "tool" && input.intent === "create" && (item.fields.sideEffect === "money" || item.fields.sideEffect === "public")) findings.push({ severity: "warn", text: `${item.name} ${item.fields.sideEffect === "money" ? "moves money" : "publishes in public"}. Attach it only to skills a policy governs.`, ref: null });
      if (input.intent === "create") findings.push({ severity: "info", text: `${item.name} is added to ${wf?.name ?? "the shared tool library"}.`, ref: null });
      if (changes.every((ch) => ["name", "description", "topics"].includes(ch.field))) findings.push({ severity: "info", text: "Only wording and topics change. Agents keep behaving the same way.", ref: null });
    }
  }

  const wordingOnly = input.intent === "update" && changes.every((ch) => ["name", "description", "topics"].includes(ch.field));
  if (wordingOnly) affected.splice(1);
  const verdict: Review["verdict"] = findings.some((f) => f.severity === "break") ? "breaking" : findings.some((f) => f.severity === "warn") || input.intent !== "update" ? "moderate" : "minimal";
  const touches = touchesFor(s, input.kind, after, before, changes);
  const base = baseLevel(input, changes, before, after);
  const escalators: string[] = [];
  if (touches.money && base.level < 3) escalators.push("touches money");
  if (touches.personal) escalators.push("touches personal data");
  if (touches.public && base.level < 3) escalators.push("touches public content");
  const clusters = new Set([wf?.clusterId, ...otherWorkflows.map((w) => workflowOf(s, w.id)?.clusterId)].filter(Boolean));
  if (clusters.size > 1) escalators.push("spans more than one cluster");
  let level = base.level;
  const reasons = [base.reason];
  if (escalators.length && level < 4) {
    level = (level + 1) as Criticality;
    reasons.push(`moves up one level because it ${escalators.join(", ")}`);
  }
  if (verdict === "breaking" && level < 2) {
    level = 2;
    reasons.push("breaking changes always need a human approver, so at least C2");
  }
  const breaks = findings.filter((f) => f.severity === "break").length;
  const warns = findings.filter((f) => f.severity === "warn").length;
  const summary = verdict === "breaking"
    ? `Breaking: ${breaks} problem${breaks > 1 ? "s" : ""} would stop part of ${wf?.name ?? "the workflow"} from working.${fixes.length ? " Apply the fixes first, or send it for approval with them noted." : ""}`
    : verdict === "moderate"
      ? `Moderate: the workflow keeps working, but behaviour changes${warns ? ` in ${warns} place${warns > 1 ? "s" : ""}` : ""}. Affects ${affected.length - 1} other item${affected.length === 2 ? "" : "s"}.`
      : "Minimal: nothing else in the workflow changes behaviour.";
  const seen = new Set<string>();
  const verb = input.intent === "create" ? "Create" : input.intent === "delete" ? "Delete" : "Update";
  return {
    input,
    title: `${verb} ${KIND_LABEL[input.kind].toLowerCase()}: ${targetName}`,
    targetName,
    changes,
    review: {
      reviewer: REVIEWER, verdict, criticality: level, criticalityReasons: reasons, summary, findings, affected, otherWorkflows,
      fixes: fixes.filter((f) => (seen.has(f.label) ? false : (seen.add(f.label), true))).slice(0, 4),
      authority: authorityFor(h, wf, level, verdict),
    },
  };
}

// ---------------------------------------------------------------- applying

export function commitInput(d: TenantData, h: Human, input: ProposalInput, nowMs: number, changeRequestId: string | null): { targetId: string; revisionId: string } {
  const s = d.studio;
  const { before, after, wf } = materialize(d, h, input);
  const at = iso(nowMs);
  const proposal = review(d, h, input);
  const target = (after ?? before)!;
  const kind: StudioKind = isWorkflow(target) ? "workflow" : target.kind;
  if (input.intent === "delete") {
    if (isWorkflow(target)) {
      const ids = new Set(target.members);
      s.items = s.items.filter((i) => !ids.has(i.id));
      s.workflows = s.workflows.filter((w) => w.id !== target.id);
    } else {
      s.items = s.items.filter((i) => i.id !== target.id);
      for (const w of s.workflows) w.members = w.members.filter((m) => m !== target.id);
    }
  } else if (isWorkflow(target)) {
    const next = { ...(after as Workflow), version: (before?.version ?? 0) + 1, updatedAt: at, updatedBy: h.id };
    s.workflows = before ? s.workflows.map((w) => (w.id === next.id ? next : w)) : [...s.workflows, next];
  } else {
    const next = { ...(after as StudioItem), version: (before?.version ?? 0) + 1, updatedAt: at, updatedBy: h.id };
    s.items = before ? s.items.map((i) => (i.id === next.id ? next : i)) : [...s.items, next];
    if (!before && wf && next.kind !== "tool") wf.members.push(next.id);
  }
  if (wf && kind !== "workflow") {
    const w = workflowOf(s, wf.id);
    if (w) {
      w.version += 1;
      w.updatedAt = at;
      w.updatedBy = h.id;
    }
  }
  d.counter += 1;
  const version = (before?.version ?? 0) + 1;
  const revisionId = `rev-${target.id}-v${version}-${d.counter.toString(36)}`;
  const summary = proposal.changes.length
    ? input.intent === "create" ? `Created ${target.name}` : input.intent === "delete" ? `Deleted ${target.name}` : proposal.changes.slice(0, 3).map((c) => `${c.label}: ${c.after ?? "cleared"}`).join("; ")
    : proposal.title;
  s.revisions.push({
    id: revisionId, targetKind: kind, targetId: target.id, workflowId: isWorkflow(target) ? target.id : target.workflowId, version, op: input.intent, at, by: h.id, summary,
    snapshot: input.intent === "delete" ? null : snapshotOf(after!), verdict: proposal.review.verdict, changeRequestId,
  });
  return { targetId: target.id, revisionId };
}

// ---------------------------------------------------------------- read models

export function summaries(d: TenantData): WorkflowSummary[] {
  return d.studio.workflows.map((wf) => {
    const counts = Object.fromEntries(MEMBER_ORDER.map((k) => [k, 0])) as Record<MemberKind, number>;
    for (const m of membersOf(d.studio, wf)) counts[m.kind] += 1;
    counts.tool = toolIdsUsedBy(d.studio, wf).length;
    const h = healthOf(d, wf);
    return {
      ...wf, counts,
      health: { breaks: h.findings.filter((f) => f.severity === "break").length, warnings: h.findings.filter((f) => f.severity === "warn").length },
      pending: d.studio.pending.filter((p) => p.workflowId === wf.id && p.status === "awaiting_approval").length,
    };
  });
}

export function detail(d: TenantData, id: string): WorkflowDetail | null {
  const wf = workflowOf(d.studio, id);
  if (!wf) return null;
  const tools = toolIdsUsedBy(d.studio, wf);
  return {
    workflow: wf,
    items: scopeOf(d.studio, wf),
    sharedToolUse: tools.map((toolId) => ({ toolId, workflows: workflowsUsingTool(d.studio, toolId).map((w) => ({ id: w.id, name: w.name })) })),
  };
}

