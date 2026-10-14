// Seeds Workflow Studio from the tenant's existing catalog. Every workflow gets its own copy of the
// skills, agents, policies, templates, sensors, schedulers and loops it needs. Tools stay shared.
import type { Criticality, ItemFields, MemberKind, Revision, Snapshot, StudioItem, Workflow } from "@/contracts";
import { TOOLS } from "../seed/catalog";
import { DAY, HOUR, SEED_NOW, hashString, iso } from "../prng";
import type { StudioData, TenantData } from "../types";

type WfDef = {
  key: string;
  name: string;
  agents: string[];
  loops: string[];
  topics: string[];
  description: string;
  criticality: Criticality;
  editors?: string[];
};

const FINEBASE_WORKFLOWS: WfDef[] = [
  { key: "care", name: "Customer care", agents: ["a-care"], loops: ["loop-care"], topics: ["support", "chat", "email", "goodwill"], criticality: 2, description: "Answers customer chat and email with cited facts, and grants small goodwill credits when usage was hurt." },
  { key: "refunds", name: "Refunds and cancellations", agents: ["a-refund"], loops: ["loop-refunds"], topics: ["refunds", "cancellations", "money"], criticality: 3, description: "Takes refund and cancellation requests, checks the window and threshold, refunds inside policy and escalates the rest." },
  { key: "billing", name: "Billing and receivables", agents: ["a-billing"], loops: ["loop-revenue"], topics: ["billing", "dunning", "receivables", "expenses"], criticality: 3, description: "Recovers failed payments, chases overdue service invoices and captures expenses from the finance inbox." },
  { key: "sales", name: "Sales pipeline", agents: ["a-sales"], loops: [], topics: ["leads", "quotes", "crm"], criticality: 2, description: "Qualifies inbound leads, follows up and drafts quotes for service projects against the rate card." },
  { key: "meetings", name: "Meetings and actions", agents: ["a-scheduler"], loops: [], topics: ["calendar", "meetings", "action items"], criticality: 1, description: "Books demos, discovery calls and sprint reviews, then turns transcripts into logged action items." },
  { key: "onboarding", name: "Client onboarding", agents: ["a-onboarding"], loops: [], topics: ["onboarding", "access", "clients"], criticality: 2, description: "Turns a signed contract into an onboarding checklist and requests the access grants the project needs." },
  { key: "delivery", name: "Client delivery reporting", agents: ["a-delivery"], loops: [], topics: ["sla", "status report", "retainers"], criticality: 2, description: "Tracks retainer SLAs from the tracker, repository and uptime monitor and sends the weekly client status report." },
  { key: "web", name: "Website content", agents: ["a-web"], loops: [], topics: ["website", "release notes", "cms"], criticality: 2, description: "Updates general website pages and release notes. Pricing and legal pages need an L1 approval." },
  { key: "ux", name: "UX experiments", agents: ["a-insights"], loops: ["loop-website"], topics: ["experiments", "clarity", "conversion"], criticality: 2, description: "Finds friction in Clarity and analytics and turns it into A/B experiments on sandbox branches." },
  { key: "reputation", name: "Reputation and reviews", agents: ["a-reputation"], loops: [], topics: ["reviews", "nps", "public replies"], criticality: 2, description: "Replies to public reviews and NPS comments in the brand tone, after a tone gate." },
  { key: "incident", name: "Incident communication", agents: ["a-incident"], loops: [], topics: ["outages", "status page", "public statements"], criticality: 3, description: "Drafts and posts outage statements when the uptime monitor reports an incident lasting five minutes." },
  { key: "compliance", name: "Compliance readiness", agents: ["a-compliance"], loops: ["loop-readiness"], topics: ["tax", "statutory", "renewals", "evidence"], criticality: 4, description: "Prepares tax and statutory evidence packs and tracks renewals. The system prepares; people file." },
  { key: "quality", name: "Overnight quality review", agents: ["a-quality"], loops: [], topics: ["failures", "fixes", "overnight"], criticality: 2, description: "Reads yesterday's runs at 02:00, classifies failures and drafts fixes as commits on sandbox branches." },
  { key: "knowledge", name: "Knowledge freshness", agents: ["a-librarian"], loops: ["loop-freshness"], topics: ["ground truth", "conflicts", "freshness"], criticality: 3, description: "Keeps ground truth worth retrieving from: finds stale and conflicting facts and proposes resolutions." },
  { key: "access", name: "Access reviews", agents: ["a-sentinel"], loops: [], topics: ["security", "grants", "access"], criticality: 3, description: "Reviews denied invocations and runs the weekly access review, then proposes grants or revocations." },
];

const CADENCE_CRON: Record<string, string> = {
  daily: "0 8 * * *",
  nightly: "0 2 * * *",
  weekly: "0 9 * * 1",
  "weekly, friday": "0 16 * * 5",
  "weekly, monday 08:00": "0 8 * * 1",
  monthly: "0 9 1 * *",
  hourly: "0 * * * *",
};

const at = (ms: number) => iso(ms);
const ago = (seedKey: string, minDays: number, spread: number) => SEED_NOW - (minDays + (hashString(seedKey) % spread)) * DAY - (hashString(`${seedKey}h`) % 20) * HOUR;

function snap(item: Pick<StudioItem, "name" | "description" | "topics" | "status" | "fields">): Snapshot {
  return { name: item.name, description: item.description, topics: [...item.topics], status: item.status, fields: structuredClone(item.fields) };
}

type Variant = { summary: string; before: (s: Snapshot) => Snapshot };

/** Writes a believable history: the current state is the newest revision; each variant describes how the one before it differed. */
function writeHistory(out: Revision[], target: { kind: Revision["targetKind"]; id: string; workflowId: string | null; version: number; dri: string }, current: Snapshot, variants: Variant[], firstSummary: string) {
  const versions = Math.max(1, Math.min(target.version, variants.length + 1));
  const states: Snapshot[] = [current];
  for (let i = 0; i < versions - 1; i++) states.unshift(variants[i].before(structuredClone(states[0])));
  const startVersion = target.version - versions + 1;
  let t = ago(target.id, 40 + versions * 25, 60);
  states.forEach((s, i) => {
    const v = startVersion + i;
    out.push({
      id: `rev-${target.id}-v${v}`, targetKind: target.kind, targetId: target.id, workflowId: target.workflowId, version: v, op: v === 1 ? "create" : "update", at: at(t), by: target.dri,
      summary: i === 0 ? (v === 1 ? firstSummary : `Version ${v}`) : variants[versions - 1 - i].summary, snapshot: s, verdict: v === 1 ? null : "minimal", changeRequestId: null,
    });
    t += (18 + (hashString(`${target.id}${v}`) % 30)) * DAY;
    if (t > SEED_NOW - DAY) t = SEED_NOW - (versions - i) * DAY;
  });
}

function sideEffect(toolId: string): string {
  if (/billing\.(refund|credit|retry)/.test(toolId)) return "money";
  if (/reviews|status\.post|cms\.publish/.test(toolId)) return "public";
  if (/\.read$/.test(toolId)) return "read";
  return "write";
}

export function emptyStudio(): StudioData {
  return { workflows: [], items: [], revisions: [], pending: [] };
}

export function seedStudio(d: TenantData): StudioData {
  return d.tenant.isScaleDemo ? seedScale(d) : seedFinebase(d);
}

function seedFinebase(d: TenantData): StudioData {
  const s = emptyStudio();
  const tenantId = d.tenant.id;

  for (const t of TOOLS) {
    const item: StudioItem = {
      id: t.id, kind: "tool", workflowId: null, name: t.label, description: `Calls ${t.label} on behalf of an agent. Needs the ${t.capability} capability.`, topics: [t.label.split(".")[0]],
      status: "active", version: 2, dri: "h-aiops",
      fields: { endpoint: `https://api.finebase.internal/${t.label.replace(".", "/")}`, capability: t.capability, sensitivity: t.sensitivity, sideEffect: sideEffect(t.id), rateLimitPerMin: sideEffect(t.id) === "money" ? 20 : 60 },
      updatedAt: at(ago(t.id, 20, 40)), updatedBy: "h-aiops",
    };
    s.items.push(item);
    writeHistory(s.revisions, { kind: "tool", id: item.id, workflowId: null, version: item.version, dri: item.dri }, snap(item), [{ summary: "Raised the rate limit", before: (x) => ({ ...x, fields: { ...x.fields, rateLimitPerMin: Number(x.fields.rateLimitPerMin) / 2 } }) }], "Registered tool");
  }

  for (const def of FINEBASE_WORKFLOWS) {
    const wfId = `wf-${def.key}`;
    const scoped = (kind: MemberKind, base: string) => `${def.key}.${kind}.${base}`;
    const members: string[] = [];
    const agents = d.agents.filter((a) => def.agents.includes(a.id));
    const skills = d.skills.filter((x) => x.branch === "main" && x.agentIds.some((a) => def.agents.includes(a)));
    const policyKeys = [...new Set(skills.flatMap((x) => x.policies))];
    const policies = policyKeys.map((k) => d.policies.filter((p) => p.key === k && p.branch === "main").sort((a, b) => b.version - a.version)[0]).filter(Boolean);
    const templates = d.templates.filter((t) => t.assignedAgents.some((a) => def.agents.includes(a)));
    const sensorIds = [...new Set(agents.flatMap((a) => a.sensors))];
    const sensors = d.sensors.filter((x) => sensorIds.includes(x.id));
    const dri = agents[0]?.dri ?? "h-founder";
    const cluster = agents[0]?.clusterId ?? d.clusters[0].id;
    const add = (item: StudioItem, variants: Variant[], first: string) => {
      s.items.push(item);
      members.push(item.id);
      writeHistory(s.revisions, { kind: item.kind, id: item.id, workflowId: wfId, version: item.version, dri: item.dri }, snap(item), variants, first);
    };
    const base = { workflowId: wfId, status: "active" as const, dri, updatedBy: dri };

    for (const x of sensors) {
      add({
        ...base, id: scoped("sensor", x.id), kind: "sensor", name: x.name, version: 2, description: `${x.source}. Emits ${x.events.join(", ")}.`, topics: [x.kind],
        fields: { source: x.source, sensorKind: x.kind, events: [...x.events], feeds: agents.filter((a) => a.sensors.includes(x.id)).map((a) => scoped("agent", a.id)), retentionDays: x.retentionDays, personalData: x.personalData, health: x.health },
        updatedAt: at(ago(x.id + def.key, 10, 50)),
      }, [{ summary: "Shortened retention to match the data retention policy", before: (v) => ({ ...v, fields: { ...v.fields, retentionDays: Number(v.fields.retentionDays) + 365 } }) }], "Connected sensor");
    }

    for (const a of agents) {
      const history: Variant[] = a.autonomy === "autonomous"
        ? [{ summary: "Promoted to autonomous after 30 days above 90% task success", before: (v) => ({ ...v, fields: { ...v.fields, autonomy: "supervised" } }) }, { summary: "Passed eval suite, promoted to supervised", before: (v) => ({ ...v, fields: { ...v.fields, autonomy: "trainee" } }) }]
        : a.autonomy === "supervised" ? [{ summary: "Passed eval suite, promoted to supervised", before: (v) => ({ ...v, fields: { ...v.fields, autonomy: "trainee" } }) }] : [];
      add({
        ...base, id: scoped("agent", a.id), kind: "agent", name: a.name, version: history.length + 1, description: a.description, topics: def.topics.slice(0, 2),
        fields: { autonomy: a.autonomy, capabilities: [...a.capabilities], accessLevel: a.accessLevel, model: a.kind === "supervisor" ? "claude-opus-5-5" : "claude-sonnet-5-5", maxConcurrent: a.kind === "supervisor" ? 2 : 4 },
        updatedAt: at(ago(a.id, 5, 30)),
      }, history, "Enrolled as trainee");
    }

    for (const p of policies) {
      const fields: ItemFields = { statement: p.statement, ruleKind: p.rule.kind, criticality: String(p.criticality), validFrom: p.validFrom.slice(0, 10) };
      for (const [k, v] of Object.entries(p.rule.params)) fields[`param.${k}`] = v;
      const item: StudioItem = { ...base, id: scoped("policy", p.key), kind: "policy", name: p.name, version: p.version, description: p.statement, topics: def.topics.slice(0, 1).concat(p.rule.kind.includes("amount") ? ["money"] : []), dri: p.dri, updatedBy: p.dri, fields, updatedAt: p.recordedAt };
      s.items.push(item);
      members.push(item.id);
      // Real policy history from the registry, newest last.
      for (const pv of d.policies.filter((x) => x.key === p.key && x.branch === "main").sort((a, b) => a.version - b.version)) {
        const f: ItemFields = { statement: pv.statement, ruleKind: pv.rule.kind, criticality: String(pv.criticality), validFrom: pv.validFrom.slice(0, 10) };
        for (const [k, v] of Object.entries(pv.rule.params)) f[`param.${k}`] = v;
        s.revisions.push({ id: `rev-${item.id}-v${pv.version}`, targetKind: "policy", targetId: item.id, workflowId: wfId, version: pv.version, op: pv.version === 1 ? "create" : "update", at: pv.recordedAt, by: pv.dri, summary: pv.version === 1 ? "Policy created" : `Changed to: ${pv.statement}`, snapshot: { name: pv.name, description: pv.statement, topics: item.topics, status: pv.supersededBy ? "retired" : "active", fields: f }, verdict: pv.version === 1 ? null : "moderate", changeRequestId: null });
      }
    }

    for (const t of templates) {
      add({
        ...base, id: scoped("template", t.id), kind: "template", name: t.name, version: 2, dri: t.owner, updatedBy: t.owner, description: `${t.cadence} report. ${t.freshnessRule}.`, topics: def.topics.slice(0, 1).concat(["report"]),
        fields: { cadence: t.cadence, fieldList: t.fields.map((f) => f.label), freshnessRule: t.freshnessRule, requiredEvidence: [...t.requiredEvidence], sensors: [...new Set(t.fields.flatMap((f) => f.sensors))].filter((x) => sensorIds.includes(x)).map((x) => scoped("sensor", x)) },
        updatedAt: at(ago(t.id, 3, 40)),
      }, [{ summary: "Added a field", before: (v) => ({ ...v, fields: { ...v.fields, fieldList: (v.fields.fieldList as string[]).slice(0, -1) } }) }], "Template created");
    }

    for (const x of skills) {
      const templateIds = [...new Set(x.templateFields.map((f) => f.split(".")[0]))].filter((id) => templates.some((t) => t.id === id));
      const hasGate = x.steps.some((st) => st.kind === "quality_gate");
      const variants: Variant[] = [
        ...(hasGate ? [{ summary: "Added a quality gate before acting", before: (v: Snapshot) => ({ ...v, fields: { ...v.fields, steps: (v.fields.steps as string[]).filter((st) => !st.startsWith("quality_gate")) } }) }] : []),
        { summary: "Tightened the trigger", before: (v) => ({ ...v, fields: { ...v.fields, trigger: `${v.fields.trigger} (after manual triage)` } }) },
        { summary: "Added a retrieval step", before: (v) => ({ ...v, fields: { ...v.fields, steps: (v.fields.steps as string[]).slice(1) } }) },
      ];
      add({
        ...base, id: scoped("skill", x.id), kind: "skill", name: x.name, version: x.version, description: `${x.trigger}. Produces ${x.outputs.join(" and ").toLowerCase()}.`, topics: def.topics.slice(0, 2),
        fields: {
          trigger: x.trigger, steps: x.steps.map((st) => `${st.kind}: ${st.text}${st.tool ? ` [${st.tool}]` : ""}`), agents: x.agentIds.filter((a) => def.agents.includes(a)).map((a) => scoped("agent", a)),
          tools: [...x.tools], policies: x.policies.map((k) => scoped("policy", k)), templates: templateIds.map((id) => scoped("template", id)),
          inputs: agents.flatMap((a) => a.sensors).filter((v, i, all) => all.indexOf(v) === i).map((v) => scoped("sensor", v)), outputs: [...x.outputs], evalCases: x.evalSuite.cases,
        },
        updatedAt: x.updatedAt,
      }, variants, "Skill authored");
    }

    // Schedulers: one per timed template cadence, plus timed triggers.
    const timed: { name: string; cron: string; skill: string | undefined }[] = [];
    for (const t of templates) {
      const cron = CADENCE_CRON[t.cadence.toLowerCase()];
      if (!cron) continue;
      const filler = skills.find((x) => x.templateFields.some((f) => f.startsWith(`${t.id}.`))) ?? skills[0];
      timed.push({ name: `Refresh ${t.name.toLowerCase()}`, cron, skill: filler?.id });
    }
    for (const x of skills) {
      const trig = x.trigger.toLowerCase();
      const cron = trig.includes("nightly at 02:00") ? "0 2 * * *" : trig.includes("weekly on friday") ? "0 16 * * 5" : trig.includes("weekly") ? "0 9 * * 1" : null;
      if (cron && !timed.some((tm) => tm.skill === x.id && tm.cron === cron)) timed.push({ name: `Run ${x.name.toLowerCase()}`, cron, skill: x.id });
    }
    if (def.key === "compliance") timed.push({ name: "Hourly readiness scan", cron: "0 * * * *", skill: "compliance-readiness" });
    timed.forEach((tm, i) => {
      const skill = skills.find((x) => x.id === tm.skill);
      add({
        ...base, id: scoped("scheduler", `sch-${i + 1}`), kind: "scheduler", name: tm.name, version: 2, description: `Wakes ${skill ? skill.name : "the workflow"} on schedule.`, topics: ["schedule"],
        fields: { cron: tm.cron, timezone: d.tenant.timezone, target: skill ? scoped("skill", skill.id) : "", agent: skill ? scoped("agent", skill.agentIds[0]) : "", enabled: true, catchUp: def.criticality >= 3 },
        updatedAt: at(ago(`${wfId}sch${i}`, 6, 30)),
      }, [{ summary: "Moved the run time", before: (v) => ({ ...v, fields: { ...v.fields, cron: String(v.fields.cron).replace(/^0 (\d+)/, (_, h) => `30 ${Math.max(0, Number(h) - 1)}`) } }) }], "Scheduler created");
    });

    for (const loopId of def.loops) {
      const l = d.loops.find((x) => x.id === loopId);
      if (!l) continue;
      const stage = (k: string) => l.stages.find((st) => st.key === k);
      const tplRef = stage("learning")?.refs.find((r) => templates.some((t) => t.id === r));
      add({
        ...base, id: scoped("loop", l.id), kind: "loop", name: `${l.name} loop`, version: 1, dri: l.dri, updatedBy: l.dri, description: l.description, topics: def.topics.slice(0, 1).concat(["improvement"]),
        fields: {
          signal: (stage("sensor")?.refs ?? []).filter((r) => sensorIds.includes(r)).map((r) => scoped("sensor", r)),
          guards: (stage("policy")?.refs ?? []).filter((r) => policyKeys.includes(r)).map((r) => scoped("policy", r)),
          actions: (stage("tool")?.refs ?? []).filter((r) => r.startsWith("tool:")),
          gate: stage("gate")?.label ?? "Quality gate", learning: tplRef ? scoped("template", tplRef) : "", reviewCadence: "Weekly",
        },
        updatedAt: at(ago(l.id, 8, 20)),
      }, [], "Loop designed");
    }

    const wf: Workflow = {
      id: wfId, tenantId, name: def.name, description: def.description, topics: def.topics, status: "active", version: 3, clusterId: cluster, dri,
      editors: def.editors ?? d.humans.filter((h) => h.tier === "L2" && h.driOf.some((x) => def.agents.includes(x) || x === cluster)).map((h) => h.id).filter((h) => h !== dri).slice(0, 2),
      criticality: def.criticality, members, updatedAt: at(ago(wfId, 2, 14)), updatedBy: dri,
    };
    s.workflows.push(wf);
    const wfSnap: Snapshot = { name: wf.name, description: wf.description, topics: wf.topics, status: wf.status, fields: { criticality: String(wf.criticality), dri: wf.dri } };
    writeHistory(s.revisions, { kind: "workflow", id: wfId, workflowId: wfId, version: wf.version, dri }, wfSnap, [
      { summary: "Added topics", before: (v) => ({ ...v, topics: v.topics.slice(0, 2) }) },
      { summary: "Rewrote the description", before: (v) => ({ ...v, description: `${def.name} workflow.` }) },
    ], "Workflow created");
  }
  return s;
}

function seedScale(d: TenantData): StudioData {
  const s = emptyStudio();
  const active = d.clusters.filter((c) => c.status === "active");
  for (let i = 0; i < 20; i++) {
    const item: StudioItem = { id: `tool:t${i}`, kind: "tool", workflowId: null, name: `tool ${i}`, description: `Generated tool ${i}.`, topics: ["generated"], status: "active", version: 1, dri: "sh-4", fields: { endpoint: `https://api.scale.internal/t${i}`, capability: `cap:${i}`, sensitivity: i % 3 ? "internal" : "confidential", sideEffect: i % 4 === 0 ? "money" : "write", rateLimitPerMin: 60 }, updatedAt: iso(SEED_NOW - (i + 3) * DAY), updatedBy: "sh-4" };
    s.items.push(item);
    s.revisions.push({ id: `rev-${item.id}-v1`, targetKind: "tool", targetId: item.id, workflowId: null, version: 1, op: "create", at: item.updatedAt, by: item.dri, summary: "Registered tool", snapshot: snap(item), verdict: null, changeRequestId: null });
  }
  active.forEach((c, ci) => {
    const key = `sc${ci}`;
    const wfId = `wf-${key}`;
    const members: string[] = [];
    const mk = (kind: MemberKind, n: number, name: string, fields: ItemFields): string => {
      const id = `${key}.${kind}.${n}`;
      const item: StudioItem = { id, kind, workflowId: wfId, name, description: `${name} (generated).`, topics: [c.name.toLowerCase()], status: "active", version: 1, dri: `sh-${ci % 3}`, fields, updatedAt: iso(SEED_NOW - (n + ci + 2) * DAY), updatedBy: `sh-${ci % 3}` };
      s.items.push(item);
      members.push(id);
      s.revisions.push({ id: `rev-${id}-v1`, targetKind: kind, targetId: id, workflowId: wfId, version: 1, op: "create", at: item.updatedAt, by: item.dri, summary: `${kind} created`, snapshot: snap(item), verdict: null, changeRequestId: null });
      return id;
    };
    const sensors = [0, 1, 2].map((n) => mk("sensor", n, `Sensor ${ci}-${n}`, { source: "Generated", sensorKind: "monitor", events: ["event"], feeds: [], retentionDays: 365, personalData: false, health: n === 2 && ci === 1 ? "down" : "ok" }));
    const agents = [0, 1].map((n) => mk("agent", n, `${c.name} agent ${n}`, { autonomy: n ? "supervised" : "autonomous", capabilities: [`cap:${ci * 3 + n}`], accessLevel: "internal", model: "claude-sonnet-5-5", maxConcurrent: 4 }));
    for (const sid of sensors) (s.items.find((x) => x.id === sid)!.fields.feeds as string[]).push(agents[0]);
    const policies = [0, 1, 2].map((n) => mk("policy", n, `${c.name} policy ${n}`, { statement: `Generated policy ${n} for ${c.name}.`, ruleKind: "max_amount_minor", criticality: String(1 + (n % 3)), validFrom: "2026-01-01", "param.amountMinor": 100_000 * (n + 1) }));
    const templates = [0, 1].map((n) => mk("template", n, `${c.name} report ${n}`, { cadence: n ? "Daily" : "Weekly", fieldList: ["Count", "Rate"], freshnessRule: "Fresh within 24 hours", requiredEvidence: [], sensors: [sensors[n]] }));
    const skills = [0, 1, 2, 3].map((n) => mk("skill", n, `${c.name} procedure ${n}`, { trigger: "Event matched by resolver", steps: ["retrieval: Retrieve context", "judgment: Decide", `tool: Act [tool:t${(ci * 3 + n) % 20}]`], agents: [agents[n % 2]], tools: [`tool:t${(ci * 3 + n) % 20}`], policies: [policies[n % 3]], templates: [templates[n % 2]], inputs: [sensors[n % 3]], outputs: ["Result"], evalCases: 30 }));
    [0, 1].forEach((n) => mk("scheduler", n, `${c.name} schedule ${n}`, { cron: n ? "0 8 * * *" : "0 9 * * 1", timezone: "UTC", target: skills[n], agent: agents[n], enabled: true, catchUp: false }));
    mk("loop", 0, `${c.name} loop`, { signal: sensors.slice(0, 2), guards: policies.slice(0, 1), actions: [`tool:t${(ci * 3) % 20}`], gate: "Quality gate", learning: templates[0], reviewCadence: "Weekly" });
    s.workflows.push({ id: wfId, tenantId: d.tenant.id, name: `${c.name} operations`, description: `Generated workflow for ${c.name}.`, topics: [c.name.toLowerCase(), "generated"], status: "active", version: 1, clusterId: c.id, dri: `sh-${ci % 3}`, editors: ["sh-3", "sh-4"], criticality: 2, members, updatedAt: iso(SEED_NOW - ci * DAY), updatedBy: `sh-${ci % 3}` });
  });
  return s;
}
