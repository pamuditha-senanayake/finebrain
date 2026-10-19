import { guideFor } from "@/lib/page-context";
import type { Analytics, AskAnswer, Human, LegibilityCell, Overview, SearchHit } from "@/contracts";
import type { ResearchSnapshot } from "@/contracts/research";
import { checkNode, humanPrincipal } from "@/lib/governance/access";
import { DAY, HOUR, hashString, iso } from "./prng";
import type { TenantData } from "./types";

const dayKey = (ms: number) => iso(ms).slice(0, 10);

export function overview(d: TenantData, now: number): Overview {
  const since = now - DAY;
  const kpis = d.clusters.map((c) => {
    const runs = d.runs.filter((r) => r.clusterId === c.id);
    const last = runs.filter((r) => Date.parse(r.startedAt) >= since);
    const done = runs.filter((r) => r.status !== "running");
    const auto = done.filter((r) => !r.humanTouch && r.status === "succeeded").length;
    const esc = done.filter((r) => r.status === "escalated" || r.humanTouch).length;
    const cost = done.reduce((s, r) => s + r.costUsd, 0);
    const resolved = done.filter((r) => r.status === "succeeded").length;
    return {
      clusterId: c.id,
      runs24h: last.length,
      autonomyRate: done.length ? auto / done.length : 0,
      escalationRate: done.length ? esc / done.length : 0,
      costPerResolvedUsd: resolved ? Math.round((cost / resolved) * 1000) / 1000 : 0,
      moneyAtStakeMinor: c.moneyAtStakeMinor,
      openRisks: c.status === "active" ? d.risks.length ? Math.max(0, Math.round(d.risks.length / 2)) + (c.id === "finance-compliance" ? 1 : 0) : c.openRisks : 0,
      health: c.health,
    };
  });
  const active = kpis.filter((k) => d.clusters.find((c) => c.id === k.clusterId)?.status === "active");
  const allDone = d.runs.filter((r) => r.status !== "running");
  const days = Array.from({ length: 14 }, (_, i) => dayKey(now - (13 - i) * DAY));
  const byDay = new Map(days.map((x) => [x, { runs: 0, auto: 0, esc: 0 }]));
  for (const r of allDone) {
    const b = byDay.get(r.startedAt.slice(0, 10));
    if (!b) continue;
    b.runs += 1;
    if (r.status === "succeeded" && !r.humanTouch) b.auto += 1;
    if (r.status === "escalated" || r.humanTouch) b.esc += 1;
  }
  const legibility: LegibilityCell[] = d.activities.map((a) => {
    const agent = d.agents.find((x) => x.id === a.agent);
    return {
      activity: a.activity, clusterId: a.cluster, agent: agent?.name ?? a.agent,
      sensed: a.sensors.length > 0 && a.sensors.every((s) => d.sensors.find((x) => x.id === s)?.health !== "down"),
      skilled: !!agent && agent.skills.length > 0,
      governed: !!agent && agent.policies.length > 0,
      reported: !!a.template && d.templates.find((t) => t.id === a.template)?.status !== "stale",
    };
  });
  return {
    kpis,
    totals: {
      runs24h: kpis.reduce((s, k) => s + k.runs24h, 0),
      autonomyRate: allDone.length ? allDone.filter((r) => r.status === "succeeded" && !r.humanTouch).length / allDone.length : 0,
      escalationRate: allDone.length ? allDone.filter((r) => r.status === "escalated" || r.humanTouch).length / allDone.length : 0,
      costPerResolvedUsd: active.length ? Math.round((active.reduce((s, k) => s + k.costPerResolvedUsd, 0) / active.length) * 1000) / 1000 : 0,
      moneyAtStakeMinor: kpis.reduce((s, k) => s + k.moneyAtStakeMinor, 0),
      openRisks: d.risks.length + d.obligations.filter((o) => o.status === "red").length,
      pendingApprovals: d.approvals.filter((a) => a.status === "pending").length,
      activeAgents: d.agents.filter((a) => a.status === "working").length,
    },
    legibility,
    trend: days.map((day) => {
      const b = byDay.get(day)!;
      return { day, runs: b.runs, autonomy: b.runs ? b.auto / b.runs : 0, escalation: b.runs ? b.esc / b.runs : 0 };
    }),
    runSeries: runSeries(d, now),
    runningNow: d.runs.filter((r) => r.status === "running").length,
    costs: {
      weekUsd: costBetween(d, now - 7 * DAY, now),
      prevWeekUsd: costBetween(d, now - 14 * DAY, now - 7 * DAY),
      monthUsd: costBetween(d, now - 30 * DAY, now),
      prevMonthUsd: costBetween(d, now - 60 * DAY, now - 30 * DAY),
    },
    entity: {
      red: d.obligations.filter((o) => o.status === "red").length,
      amber: d.obligations.filter((o) => o.status === "amber").length,
      risks: d.risks.length,
      evidenceOpen: d.evidenceRequests.filter((e) => e.status === "open" || e.status === "awaiting_grant_approval").length,
    },
  };
}

const SLOT = HOUR / 2;

function runSeries(d: TenantData, now: number) {
  const end = Math.floor(now / SLOT) * SLOT + SLOT;
  const start = end - 48 * SLOT;
  const counts = new Array<number>(48).fill(0);
  for (const r of d.runs) {
    const t = Date.parse(r.startedAt);
    if (t >= start && t < end) counts[Math.floor((t - start) / SLOT)] += 1;
  }
  return counts.map((runs, i) => ({ at: iso(start + i * SLOT), runs }));
}

function costBetween(d: TenantData, from: number, to: number) {
  let sum = 0;
  for (const r of d.runs) {
    const t = Date.parse(r.startedAt);
    if (t >= from && t < to) sum += r.costUsd;
  }
  return Math.round(sum * 100) / 100;
}

export function analytics(d: TenantData, now: number): Analytics {
  const days = Array.from({ length: 14 }, (_, i) => dayKey(now - (13 - i) * DAY));
  return {
    clusters: d.clusters.filter((c) => c.status === "active").map((c) => {
      const runs = d.runs.filter((r) => r.clusterId === c.id);
      return {
        clusterId: c.id, name: c.name,
        series: days.map((day) => {
          const dayRuns = runs.filter((r) => r.startedAt.startsWith(day));
          const auto = dayRuns.filter((r) => r.status === "succeeded" && !r.humanTouch).length;
          return { day, runs: dayRuns.length, autonomy: dayRuns.length ? auto / dayRuns.length : 0, cost: Math.round(dayRuns.reduce((s, r) => s + r.costUsd, 0) * 100) / 100 };
        }),
      };
    }),
    loops: d.loops.map((l) => ({ id: l.id, name: l.name, successRate: l.successRate, autonomyRate: l.autonomyRate, runs7d: l.runs7d })),
    experiments: d.experiments.map((e) => ({ id: e.id, title: e.title, status: e.status, impact: e.impact })),
    templates: d.templates.slice(0, 40).map((t) => ({ id: t.id, name: t.name, completion: t.fields.filter((f) => f.value).length / Math.max(1, t.fields.length), status: t.status })),
  };
}

export function search(d: TenantData, q: string): SearchHit[] {
  const term = q.trim().toLowerCase();
  if (term.length < 2) return [];
  const hits: SearchHit[] = [];
  const push = (h: SearchHit) => hits.length < 30 && hits.push(h);
  for (const a of d.agents) if (a.name.toLowerCase().includes(term)) push({ id: a.id, kind: "Agent", label: a.name, href: `/l3/agents/${a.id}`, hint: a.description });
  for (const s of d.skills.filter((x) => x.branch === "main")) if (s.name.toLowerCase().includes(term) || s.id.includes(term)) push({ id: s.id, kind: "Skill", label: `${s.name} v${s.version}`, href: `/l2/skills/${s.id}?focus=skill:${s.id}`, hint: s.trigger, focus: { kind: "skill", id: s.id } });
  for (const p of d.policies.filter((x) => !x.supersededBy)) if (p.name.toLowerCase().includes(term) || p.key.includes(term)) push({ id: p.id, kind: "Policy", label: `${p.name} v${p.version}`, href: `/l2/policies/${p.key}?focus=policy:${p.key}&q=${encodeURIComponent(term)}`, hint: p.statement, focus: { kind: "policy", id: p.key } });
  for (const f of d.facts) if (f.statement.toLowerCase().includes(term)) push({ id: f.id, kind: "Fact", label: f.statement, href: `/l2/vault?fact=${f.id}`, hint: f.status });
  for (const a of d.approvals.filter((x) => x.status === "pending")) if (a.title.toLowerCase().includes(term)) push({ id: a.id, kind: "Approval", label: a.title, href: `/l1/approvals/${a.id}`, hint: `C${a.criticality}` });
  for (const o of d.obligations) if (o.title.toLowerCase().includes(term)) push({ id: o.id, kind: "Obligation", label: o.title, href: "/l1/entity", hint: `${o.readiness}% ready` });
  for (const c of d.conversations) if (c.topic.toLowerCase().includes(term) || c.customer.toLowerCase().includes(term)) push({ id: c.id, kind: "Conversation", label: `${c.customer} · ${c.topic}`, href: `/l3/conversations/${c.id}`, hint: c.status });
  for (const r of d.runs) if (r.id === term || r.subject.toLowerCase().includes(term)) push({ id: r.id, kind: "Run", label: r.subject, href: `/l3/runs?focus=run:${r.id}`, hint: r.status, focus: { kind: "run", id: r.id } });
  return hits;
}

const STOP = new Set(["what", "is", "the", "a", "an", "for", "of", "our", "do", "we", "how", "when", "does", "are", "to", "in", "on", "and", "with", "can", "i", "my"]);

/** Answers only from facts the asker may see, with valid time on every citation. */
/** One line of live numbers for the page a person is on, so "this page" answers use real data. */
function pageLine(d: TenantData, key: string): string | null {
  const pending = d.approvals.filter((a) => a.status === "pending").length;
  switch (key) {
    case "approvals": case "digest": case "overview": return `${pending} approval${pending === 1 ? " is" : "s are"} pending.`;
    case "entity": return `${d.obligations.filter((o) => o.status === "red").length} obligations are red and ${d.obligations.filter((o) => o.status === "amber").length} amber; ${d.risks.length} risks are registered.`;
    case "evidence": return `${d.evidenceRequests.filter((r) => r.status !== "fulfilled").length} evidence requests are open.`;
    case "library": return `${d.documents.length} documents, ${d.documents.filter((x) => x.sensitivity === "restricted").length} restricted, ${d.documents.filter((x) => x.personalData).length} with personal data.`;
    case "vault": return `${d.facts.filter((f) => f.status === "unverified").length} unverified and ${d.facts.filter((f) => f.status === "conflicted").length} conflicted facts.`;
    case "policies": case "policy": return `${d.policies.filter((p) => !p.supersededBy && p.branch === "main").length} current policies.`;
    case "skills": return `${d.skills.filter((x) => x.branch === "main").length} skills on main.`;
    default: return null;
  }
}

export function ask(d: TenantData, asker: Human, question: string, now: number, page?: { path: string; scope: "page" | "system" }): AskAnswer {
  if (page?.scope === "page") {
    const guide = guideFor(page.path);
    const words = question.toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 2 && !STOP.has(w));
    const tips = guide.tips.filter((t) => words.some((w) => t.toLowerCase().includes(w)));
    const facts = ask(d, asker, question, now);
    const live = pageLine(d, guide.key);
    const lead = `${guide.title}: ${guide.summary}`;
    const body = [facts.citations.length ? facts.answer : null, live].filter(Boolean).join(" "); // the answer first, then the page
    return { ...facts, answer: body ? `${body}` : lead, scope: "page", guide: tips.length ? tips : guide.tips, actions: guide.links };
  }
  return { ...askSystem(d, asker, question, now), scope: "system" };
}

function askSystem(d: TenantData, asker: Human, question: string, now: number): AskAnswer {
  const words = question.toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 2 && !STOP.has(w));
  const principal = humanPrincipal(asker);
  const scored = d.facts
    .filter((f) => f.status !== "superseded")
    .map((f) => ({ f, score: words.filter((w) => `${f.statement} ${f.subject}`.toLowerCase().includes(w)).length }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || (a.f.validFrom < b.f.validFrom ? 1 : -1));
  const allowed = scored.filter(({ f }) => checkNode(principal, { sensitivity: f.sensitivity, requires: { capability: null, roles: [] }, label: f.statement }).allowed);
  const withheld = scored.length - allowed.length;
  const top = allowed.slice(0, 3).map((x) => x.f);
  const policies = d.policies.filter((p) => !p.supersededBy && words.some((w) => `${p.name} ${p.statement}`.toLowerCase().includes(w))).slice(0, 2);
  if (!top.length && !policies.length) {
    return { question, answer: withheld ? "I found facts that match, but your access level does not include them." : "I could not find a verified fact for that. Ask the Librarian to add one, or rephrase.", citations: [], withheld };
  }
  const future = top.filter((f) => Date.parse(f.validFrom) > now);
  const current = top.filter((f) => Date.parse(f.validFrom) <= now);
  const lines: string[] = [];
  if (current.length) lines.push(current.map((f) => f.statement).join(". ") + ".");
  if (policies.length) lines.push(`Policy: ${policies.map((p) => `${p.name} v${p.version}: ${p.statement}`).join(" ")}`);
  if (future.length) lines.push(`Coming change: ${future.map((f) => `${f.statement} (true from ${f.validFrom.slice(0, 10)}, ${f.status})`).join(". ")}.`);
  return {
    question,
    answer: lines.join(" "),
    citations: [
      ...top.map((f) => ({ id: f.id, kind: "fact", label: f.statement, validFrom: f.validFrom, validTo: f.validTo, href: `/l2/vault?fact=${f.id}` })),
      ...policies.map((p) => ({ id: p.id, kind: "policy", label: `${p.name} v${p.version}`, validFrom: p.validFrom, validTo: p.validTo, href: `/l2/policies/${p.key}` })),
    ],
    withheld,
  };
}

function series(seed: string, n: number, base: number, spread: number) {
  return Array.from({ length: n }, (_, i) => ({ x: `w${i + 1}`, y: Math.round((base + (((hashString(`${seed}${i}`) % 1000) / 1000) - 0.5) * spread) * 1000) / 1000 }));
}

/** Research metrics aggregated from the same events the product shows. All values are SAMPLE until real experiment output is imported. */
export function researchSnapshots(d: TenantData, now: number): ResearchSnapshot[] {
  const skills = d.skills.filter((s) => s.branch === "main");
  const avg = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
  const denials = d.accessDecisions.filter((a) => a.decision === "deny").length;
  const policies = d.policies.filter((p) => !p.supersededBy);
  const meta = { isSample: true, source: "Mock event stream (SAMPLE)", takenAt: iso(now) };
  return [
    { paper: "skills", title: "Skills: documented procedure vs observed work", ...meta, metrics: [
      { key: "conformance", label: "Skill conformance to observed runs", definition: "Share of observed run steps that match the documented skill steps, averaged over active skills.", value: avg(skills.map((s) => s.health.conformance)), unit: "ratio", condition: "production", series: series("conf", 8, 0.84, 0.1) },
      { key: "gap", label: "Documented vs observed gap", definition: "1 minus conformance, averaged over skills with at least 20 runs.", value: 1 - avg(skills.map((s) => s.health.conformance)), unit: "ratio", condition: "production", series: series("gap", 8, 0.16, 0.08) },
      { key: "success", label: "Task success", definition: "Runs that ended succeeded without a human, over all finished runs.", value: avg(skills.map((s) => s.health.taskSuccess)), unit: "ratio", condition: "production", series: series("succ", 8, 0.87, 0.08) },
      { key: "passk", label: "Consistency pass^k (k=8)", definition: "Probability that all k repeated runs of the same eval case pass.", value: avg(skills.map((s) => s.health.consistencyPassK)), unit: "ratio", condition: "sandbox evals", series: series("pk", 8, 0.82, 0.1) },
    ] },
    { paper: "policies", title: "Policies: freshness and drift", ...meta, metrics: [
      { key: "signals", label: "Policies with an active freshness signal", definition: "Policies where any of the five signals fired: interval closed, drift point, low conformance, conflicting evidence, outdated reliance.", value: policies.filter((p) => p.freshness.driftPointAt || p.freshness.conflictingEvidence || p.freshness.conformance < 0.8).length, unit: "count", condition: "production", series: series("sig", 8, 2, 2) },
      { key: "expired", label: "Actions under expired policy", definition: "Runs whose governing policy had a closed validity interval at run time, over all runs.", value: 0.004, unit: "ratio", condition: "production", series: series("exp", 8, 0.005, 0.006) },
      { key: "recall", label: "Drift detection recall", definition: "Injected drifts detected within 7 days, over injected drifts.", value: 0.83, unit: "ratio", condition: "injected drift", series: series("rec", 8, 0.8, 0.12) },
      { key: "delay", label: "Drift detection delay", definition: "Median hours from drift onset to first signal.", value: 31, unit: "count", condition: "injected drift", series: series("del", 8, 30, 14) },
      { key: "asof", label: "'As of now' returns current version", definition: "Share of as of now queries that returned the version valid now.", value: 0.998, unit: "ratio", condition: "production", series: series("asof", 8, 0.997, 0.004) },
    ] },
    { paper: "security", title: "Security: leakage and enforcement", ...meta, metrics: [
      { key: "leak", label: "Leakage rate, combined role and attribute rules", definition: "Restricted items that appeared in an answer for a principal without access, over answers.", value: 0, unit: "ratio", condition: "graph enforcement", series: series("leak", 8, 0.0, 0.0) },
      { key: "leak-base", label: "Leakage rate, retrieval time filtering baseline", definition: "Same as above with filtering only at retrieval time.", value: 0.031, unit: "ratio", condition: "baseline", series: series("leakb", 8, 0.03, 0.02) },
      { key: "denied", label: "Unauthorized invocations denied", definition: "Denied access decisions in the window.", value: denials, unit: "count", condition: "production", series: series("den", 8, denials / 8, 4) },
      { key: "latency", label: "Enforcement latency p95", definition: "95th percentile of access decision latency.", value: Math.round(Math.max(...d.accessDecisions.slice(0, 500).map((a) => a.latencyMs), 0) * 10) / 10, unit: "ms", condition: "production", series: series("lat", 8, 9, 3) },
    ] },
    { paper: "integration", title: "Integration: brain vs retrieval only", ...meta, metrics: [
      { key: "completion", label: "Task completion", definition: "Tasks completed end to end without a human.", value: 0.81, unit: "ratio", condition: "company brain", series: series("tc", 8, 0.8, 0.06) },
      { key: "completion-base", label: "Task completion, retrieval only", definition: "Same tasks with a retrieval only agent.", value: 0.58, unit: "ratio", condition: "baseline", series: series("tcb", 8, 0.58, 0.08) },
      { key: "pass1", label: "pass^1", definition: "Single attempt pass rate on the integration suite.", value: 0.84, unit: "ratio", condition: "company brain", series: series("p1", 8, 0.84, 0.05) },
      { key: "pass8", label: "pass^8", definition: "All 8 attempts pass.", value: 0.66, unit: "ratio", condition: "company brain", series: series("p8", 8, 0.66, 0.08) },
      { key: "stale", label: "Stale answer rate", definition: "Answers citing a fact whose validity had closed.", value: 0.012, unit: "ratio", condition: "company brain", series: series("st", 8, 0.012, 0.01) },
    ] },
  ];
}
