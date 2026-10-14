// The Studio assistant's mock brain: a rule based intent engine. It reads loose requests, finds what they are about,
// asks when it is unsure, suggests concrete edits, and hands every edit to the Edit Review Agent before anyone confirms.
// A real LLM endpoint can replace `chat` later; the request and reply contracts stay the same.
import type { ChatReply, ChatRequest, FieldValue, Human, ItemFields, MemberKind, Proposal, ProposalInput, Revision, StudioCard, StudioItem, StudioKind, Suggestion, Workflow } from "@/contracts";
import {
  COMMON_FIELDS,
  FIELD_SPECS,
  KIND_LABEL,
  KIND_PLURAL,
  KIND_SYNONYMS,
  MEMBER_ORDER,
  PARAM_SYNONYMS,
  describeCron,
  fieldLabel,
  formatValue,
  isParam,
  paramName,
  refsOf,
  validCron,
  type FieldSpec,
} from "@/lib/studio/spec";
import type { TenantData } from "../types";
import { REVIEWER, StudioError, healthOf, itemOf, membersOf, nameOf, review, scopeOf, workflowOf, workflowsUsingTool } from "./engine";

type Target = { kind: StudioKind; item: StudioItem | null; wf: Workflow | null; id: string; name: string };

const STOP = new Set("the a an to of for in on and or with it its this that these those please can could would you me my our we is are be been make set change update edit add remove delete new create show what how why which who whom from by at as into more less so do does did i let lets want need should will just also all any some there their them then than up down out about give tell list explain".split(" "));

const stem = (w: string) => (w.length > 4 && w.endsWith("ies") ? `${w.slice(0, -3)}y` : w.length > 3 && w.endsWith("s") && !w.endsWith("ss") ? w.slice(0, -1) : w);
const words = (s: string) => s.toLowerCase().replace(/[^a-z0-9:.\s-]/g, " ").split(/[\s.\-:]+/).filter(Boolean);
const tokens = (s: string) => words(s).filter((w) => !STOP.has(w)).map(stem);
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const money = (minor: number, cur: string) => `${cur} ${(minor / 100).toLocaleString("en-US")}`;

// ---------------------------------------------------------------- cards

function itemCard(it: StudioItem | Workflow, current = true): StudioCard {
  const isWf = "members" in it;
  const kind: StudioKind = isWf ? "workflow" : it.kind;
  const key = isWf ? [] : keyFields(it).slice(0, 2).map(([k, v]) => `${k}: ${v}`);
  return {
    id: `card-${it.id}`, kind, targetId: it.id, workflowId: isWf ? it.id : it.workflowId, title: it.name, subtitle: `${KIND_LABEL[kind]} · v${it.version}`,
    body: [it.description, ...key].filter(Boolean).join(" · ").slice(0, 220), badges: [it.status, ...it.topics.slice(0, 2)], current, at: it.updatedAt,
  };
}

function revisionCard(r: Revision, currentVersion: number): StudioCard {
  const s = r.snapshot;
  const extra = s && r.targetKind === "policy" ? Object.entries(s.fields).filter(([k]) => isParam(k)).map(([k, v]) => `${fieldLabel("policy", k)}: ${formatValue(v, paramName(k))}`).join(" · ") : "";
  return {
    id: `card-${r.id}`, kind: r.targetKind, targetId: r.targetId, workflowId: r.workflowId, title: `${s?.name ?? "Deleted"} v${r.version}`, subtitle: `${r.op === "create" ? "Created" : r.op === "delete" ? "Deleted" : "Changed"}${r.version === currentVersion ? " · current" : ""}`,
    body: [r.summary, extra].filter(Boolean).join(" · ").slice(0, 220), badges: [r.verdict ?? r.op, ...(r.changeRequestId ? [r.changeRequestId] : [])], current: r.version === currentVersion, at: r.at,
  };
}

export function historyOf(d: TenantData, targetId: string) {
  return d.studio.revisions.filter((r) => r.targetId === targetId).sort((a, b) => b.version - a.version || (a.at < b.at ? 1 : -1));
}

function historyCards(d: TenantData, t: StudioItem | Workflow, n = 4) {
  return historyOf(d, t.id).slice(0, n).map((r) => revisionCard(r, t.version));
}

function keyFields(it: StudioItem): [string, string][] {
  const out: [string, string][] = [];
  const s = it.kind ? FIELD_SPECS[it.kind] : [];
  for (const spec of s) {
    const v = it.fields[spec.key];
    if (v === undefined || v === "" || (Array.isArray(v) && !v.length)) continue;
    const shown = spec.type === "refs" || spec.type === "ref" ? (Array.isArray(v) ? v : [String(v)]).map((id) => id.startsWith("tool:") ? id.replace("tool:", "") : id).map((id) => id.includes(".") && !id.startsWith("tool") ? id : id).join(", ") : spec.key === "cron" ? `${describeCron(String(v))} (${v})` : formatValue(v, spec.key);
    out.push([spec.label, shown]);
  }
  for (const [k, v] of Object.entries(it.fields)) if (isParam(k)) out.push([fieldLabel(it.kind, k), paramName(k) === "amountMinor" ? money(Number(v), String(it.fields["param.currency"] ?? "LKR")) : formatValue(v, paramName(k))]);
  return out;
}

function readableFields(d: TenantData, it: StudioItem): string[] {
  return keyFields(it).map(([k, v]) => `${k}: ${v.split(", ").map((id) => (itemOf(d.studio, id)?.name ?? id)).join(", ")}`);
}

// ---------------------------------------------------------------- understanding

function kindIn(text: string): StudioKind | null {
  let best: { kind: StudioKind; at: number } | null = null;
  for (const k of [...MEMBER_ORDER, "workflow"] as StudioKind[]) {
    for (const syn of KIND_SYNONYMS[k]) {
      const m = new RegExp(`\\b${syn}\\b`).exec(text);
      if (m && (!best || m.index < best.at)) best = { kind: k, at: m.index };
    }
  }
  return best?.kind ?? null;
}

function score(text: string, textTokens: Set<string>, name: string): number {
  const nt = tokens(name).filter((t) => t.length > 2);
  if (!nt.length) return 0;
  const hit = nt.filter((t) => textTokens.has(t)).length;
  if (!hit) return 0;
  let sc = hit / nt.length;
  if (text.includes(name.toLowerCase())) sc += 0.6;
  return sc;
}

type Cand = { t: Target; score: number };

function candidates(d: TenantData, wf: Workflow, text: string, kindHint: StudioKind | null, only?: MemberKind): Cand[] {
  const tt = new Set(tokens(text));
  const out: Cand[] = [];
  for (const it of scopeOf(d.studio, wf)) {
    if (only && it.kind !== only) continue;
    let sc = score(text, tt, it.name);
    if (it.kind === "tool") sc = Math.max(sc, text.includes(it.name.toLowerCase()) ? 1.4 : 0);
    if (!sc) continue;
    if (kindHint === it.kind) sc += 0.35;
    if (!kindHint && it.kind === "policy" && directionIn(text)) sc += 0.4;
    out.push({ t: { kind: it.kind, item: it, wf: null, id: it.id, name: it.name }, score: sc });
  }
  if (!only) {
    const sc = score(text, tt, wf.name) + (kindHint === "workflow" ? 0.5 : 0);
    if (sc > 0) out.push({ t: { kind: "workflow", item: null, wf, id: wf.id, name: wf.name }, score: sc - 0.15 });
  }
  return out.sort((a, b) => b.score - a.score);
}

const PRONOUN = /\b(it|this|that|its|this one|the same)\b/;

function resolve(d: TenantData, wf: Workflow, text: string, focus: ChatRequest["focus"], kindHint: StudioKind | null, only?: MemberKind): { target: Target | null; ambiguous: Cand[] } {
  const cands = candidates(d, wf, text, kindHint, only).filter((c) => c.score >= 0.5);
  const focusTarget = (): Target | null => {
    if (!focus) return null;
    if (focus.kind === "workflow") return focus.id === wf.id ? { kind: "workflow", item: null, wf, id: wf.id, name: wf.name } : null;
    const it = itemOf(d.studio, focus.id);
    return it && (!only || it.kind === only) ? { kind: it.kind, item: it, wf: null, id: it.id, name: it.name } : null;
  };
  if (!cands.length) {
    if (PRONOUN.test(text) || !kindHint || (focus && focus.kind === kindHint)) return { target: focusTarget(), ambiguous: [] };
    return { target: null, ambiguous: [] };
  }
  const top = cands[0];
  const close = cands.filter((c) => c.score >= top.score - 0.05 && c.t.id !== top.t.id && c.t.kind === top.t.kind);
  if (close.length && top.score < 1.2) return { target: null, ambiguous: [top, ...close].slice(0, 4) };
  return { target: top.t, ambiguous: [] };
}

function fieldIn(kind: StudioKind, text: string, item: StudioItem | null): string | null {
  let best: { key: string; len: number } | null = null;
  const consider = (key: string, syns: string[]) => {
    for (const syn of syns) if (new RegExp(`\\b${syn}\\b`).test(text) && (!best || syn.length > best.len)) best = { key, len: syn.length };
  };
  if (item?.kind === "policy") for (const k of Object.keys(item.fields).filter(isParam)) consider(k, PARAM_SYNONYMS[paramName(k)] ?? [paramName(k)]);
  const specs: FieldSpec[] = kind === "workflow" ? COMMON_FIELDS : [...COMMON_FIELDS, ...FIELD_SPECS[kind]];
  for (const spec of specs) consider(spec.key, [spec.label.toLowerCase(), ...(spec.synonyms ?? [])]);
  return (best as { key: string } | null)?.key ?? null;
}

function numberIn(text: string): number | null {
  const m = text.match(/(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|m|million|lakh)?\b/);
  if (!m) return null;
  const n = Number(m[1].replace(/,/g, ""));
  const mult = m[2] === "k" || m[2] === "thousand" ? 1_000 : m[2] === "m" || m[2] === "million" ? 1_000_000 : m[2] === "lakh" ? 100_000 : 1;
  return Number.isFinite(n) ? n * mult : null;
}

function quoted(text: string): string | null {
  return text.match(/["“']([^"”']{2,})["”']/)?.[1] ?? null;
}

function afterTo(raw: string): string | null {
  const q = quoted(raw);
  if (q) return q;
  const m = raw.match(/\b(?:to|as|=|:)\s+(.+)$/i);
  return m ? m[1].trim().replace(/[.]$/, "") : null;
}

const DOW: Record<string, number> = { sunday: 0, sun: 0, monday: 1, mon: 1, tuesday: 2, tue: 2, wednesday: 3, wed: 3, thursday: 4, thu: 4, friday: 5, fri: 5, saturday: 6, sat: 6 };

export function cronIn(text: string): string | null {
  const explicit = text.match(/([0-9*,\-/]+\s+[0-9*,\-/]+\s+[0-9*,\-/]+\s+[0-9*,\-/]+\s+[0-9*,\-/a-z]+)/);
  if (explicit && validCron(explicit[1])) return explicit[1];
  if (/\b(hourly|every hour)\b/.test(text)) return "0 * * * *";
  const tm = text.match(/\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b/) ?? text.match(/\b(\d{1,2})(?::(\d{2}))\s*(am|pm)?\b/) ?? text.match(/\b(\d{1,2})\s*(am|pm)\b/);
  let h: number | null = null;
  let m = 0;
  if (tm) {
    h = Number(tm[1]);
    const mins = tm[2] && /^\d{2}$/.test(tm[2]) ? Number(tm[2]) : 0;
    m = mins;
    const ampm = tm[3] ?? (tm[2] && !/^\d{2}$/.test(tm[2]) ? tm[2] : undefined);
    if (ampm === "pm" && h < 12) h += 12;
    if (ampm === "am" && h === 12) h = 0;
    if (h > 23) h = null;
  }
  if (h === null) {
    if (/\bmorning\b/.test(text)) h = 8;
    else if (/\b(evening|end of day)\b/.test(text)) h = 18;
    else if (/\bnight(ly)?\b/.test(text)) h = 2;
    else if (/\bnoon\b/.test(text)) h = 12;
  }
  const day = Object.keys(DOW).find((k) => new RegExp(`\\b${k}s?\\b`).test(text));
  const hh = h ?? 9;
  if (/\bweekdays?\b/.test(text)) return `${m} ${hh} * * 1-5`;
  if (day) return `${m} ${hh} * * ${DOW[day]}`;
  if (/\bmonthly|every month|each month\b/.test(text)) {
    const dom = text.match(/\b(\d{1,2})(?:st|nd|rd|th)\b/);
    return `${m} ${hh} ${dom ? dom[1] : 1} * *`;
  }
  if (/\bweekly|every week\b/.test(text)) return `${m} ${hh} * * 1`;
  if (/\b(daily|every day|each day|nightly|every night|every morning|every evening)\b/.test(text) || h !== null) return `${m} ${hh} * * *`;
  return null;
}

function boolIn(text: string): boolean | null {
  if (/\b(on|yes|true|enable|enabled|turn on|start)\b/.test(text)) return true;
  if (/\b(off|no|false|disable|disabled|turn off|stop)\b/.test(text)) return false;
  return null;
}

type Direction = "stricter" | "looser" | null;
function directionIn(text: string): Direction {
  if (/\b(strict|stricter|tight|tighter|tighten|safer|safe|lower|reduce|decrease|shorter|shorten|less|cut|conservative|smaller)\b/.test(text)) return "stricter";
  if (/\b(loose|looser|loosen|relax|lenient|higher|raise|increase|longer|extend|more|bigger|generous)\b/.test(text)) return "looser";
  return null;
}

// ---------------------------------------------------------------- guidance

function upd(t: StudioItem | Workflow, patch: ProposalInput["patch"]): ProposalInput {
  const isWf = "members" in t;
  return { intent: "update", kind: isWf ? "workflow" : t.kind, targetId: t.id, workflowId: isWf ? t.id : t.workflowId, patch };
}

function sug(label: string, input: ProposalInput, tone: Suggestion["tone"] = "neutral"): Suggestion {
  return { label, prompt: label, tone, input };
}

function ask(label: string, prompt = label): Suggestion {
  return { label, prompt, tone: "neutral" };
}

export function describe(d: TenantData, t: StudioItem | Workflow): string {
  const s = d.studio;
  const names = (v: FieldValue | undefined) => (Array.isArray(v) ? v : v ? [String(v)] : []).map((id) => nameOf(s, id)).join(", ") || "nothing yet";
  if ("members" in t) {
    const ms = membersOf(s, t);
    const count = (k: MemberKind) => ms.filter((m) => m.kind === k).length;
    return `${t.description.split(".")[0]}. ${count("agent")} agent${count("agent") === 1 ? "" : "s"} run ${count("skill")} skill${count("skill") === 1 ? "" : "s"} under ${count("policy")} polic${count("policy") === 1 ? "y" : "ies"}, fed by ${count("sensor")} sensor${count("sensor") === 1 ? "" : "s"} and ${count("scheduler")} schedule${count("scheduler") === 1 ? "" : "s"}, reporting into ${count("template")} template${count("template") === 1 ? "" : "s"}.`;
  }
  const f = t.fields;
  switch (t.kind) {
    case "skill": {
      const steps = ((f.steps as string[]) ?? []).map((x) => x.replace(/^[a-z_]+:\s*/, "").replace(/\s*\[.*\]$/, "").toLowerCase());
      return `Runs when ${String(f.trigger ?? "triggered").replace(/^./, (c) => c.toLowerCase())}. ${steps.length} steps: ${steps.join(", then ")}. Run by ${names(f.agents)}, uses ${names(f.tools)}, governed by ${names(f.policies)}.`;
    }
    case "policy":
      return String(f.statement || t.description);
    case "agent":
      return `${t.name} works ${f.autonomy} at ${f.accessLevel} access, holding ${((f.capabilities as string[]) ?? []).join(", ") || "no capabilities"}.`;
    case "scheduler":
      return `${describeCron(String(f.cron ?? ""))} (${f.timezone}), runs ${names(f.target)} on ${names(f.agent)}.${f.enabled === false ? " Currently turned off." : ""}`;
    case "template":
      return `${f.cadence} report with ${((f.fieldList as string[]) ?? []).join(", ") || "no fields yet"}. ${f.freshnessRule}.`;
    case "sensor":
      return `${f.source}: emits ${((f.events as string[]) ?? []).join(", ")}. Feeds ${names(f.feeds)}. Keeps data for ${f.retentionDays} days${f.personalData ? " and carries personal data" : ""}.`;
    case "loop":
      return `Senses ${names(f.signal)}, guarded by ${names(f.guards)}, acts with ${names(f.actions)}, checks ${f.gate}, and learns into ${names(f.learning)}.`;
    case "tool":
      return `A ${f.sideEffect} tool at ${f.endpoint}. Agents need ${f.capability} to call it. Rate limit ${f.rateLimitPerMin} per minute.`;
  }
}

function topicIdeas(t: StudioItem | Workflow): string[] {
  const pool = tokens(`${t.name} ${t.description}`).filter((w) => w.length > 4 && !t.topics.includes(w));
  return [...new Set(pool)].slice(0, 3);
}

function guidance(d: TenantData, t: StudioItem | Workflow, dir: Direction = null): Suggestion[] {
  const out: Suggestion[] = [];
  const s = d.studio;
  if ("members" in t) {
    out.push(sug("Rewrite the description from what it contains", upd(t, { description: describe(d, t) })));
    const ideas = topicIdeas(t);
    if (ideas.length) out.push(sug(`Add topics: ${ideas.join(", ")}`, upd(t, { topics: [...t.topics, ...ideas] })));
    out.push(t.status === "active" ? sug("Pause the whole workflow", upd(t, { status: "paused" })) : sug("Resume the workflow", upd(t, { status: "active" })));
    out.push(ask("Check the workflow for problems", "What is broken in this workflow?"));
    return out;
  }
  const f = t.fields;
  if (t.kind === "policy") {
    const cur = String(f["param.currency"] ?? d.tenant.currency);
    for (const k of Object.keys(f).filter(isParam)) {
      const v = f[k];
      const p = paramName(k);
      if (typeof v === "number" && p !== "currency") {
        const fmt = (n: number) => (p === "amountMinor" ? money(n, cur) : `${n}${/days$/i.test(p) ? " days" : ""}`);
        const round = (n: number) => (p === "amountMinor" ? Math.max(100_000, Math.round(n / 100_000) * 100_000) : /days$/i.test(p) && n >= 14 ? Math.round(n / 7) * 7 : Math.max(1, Math.round(n)));
        const label = fieldLabel("policy", k).toLowerCase();
        const opts: [string, number, Suggestion["tone"]][] = v === 0
          ? [["Looser", round(p === "amountMinor" ? 1_000_000 : 7), "neutral"]]
          : dir === "stricter" ? [["A bit stricter", round(v * 0.75), "primary"], ["Much stricter", round(v * 0.5), "neutral"]]
          : dir === "looser" ? [["A bit looser", round(v * 1.25), "primary"], ["Much looser", round(v * 1.5), "neutral"]]
          : [["Stricter", round(v * 0.5), "primary"], ["Looser", round(v * 1.5), "neutral"]];
        for (const [name, n, tone] of opts) if (n !== v && !out.some((o) => o.input?.patch.fields?.[k] === n)) out.push(sug(`${name}: ${label} ${fmt(v)} → ${fmt(n)}`, upd(t, { fields: { [k]: n } }), tone));
      }
      if (typeof v === "boolean") out.push(sug(`${v ? "Turn off" : "Turn on"} ${fieldLabel("policy", k).toLowerCase()}`, upd(t, { fields: { [k]: !v } })));
    }
    out.push(ask("Reword the statement", `Change the statement of ${t.name} to "…"`));
  }
  if (t.kind === "skill") {
    const steps = (f.steps as string[]) ?? [];
    if (!steps.some((x) => x.startsWith("quality_gate"))) {
      const at = Math.max(0, steps.findIndex((x) => x.startsWith("tool")));
      const next = [...steps];
      next.splice(at === -1 ? next.length : at, 0, "quality_gate: Check grounding and policy before acting");
      out.push(sug("Add a quality gate before it acts", upd(t, { fields: { steps: next } }), "primary"));
    }
    const policies = membersOf(s, s.workflows.find((w) => w.id === t.workflowId)!).filter((m) => m.kind === "policy" && !((f.policies as string[]) ?? []).includes(m.id));
    if (policies[0]) out.push(sug(`Govern it by ${policies[0].name}`, upd(t, { fields: { policies: [...((f.policies as string[]) ?? []), policies[0].id] } })));
    const cases = Number(f.evalCases ?? 0);
    out.push(sug(`Raise eval cases from ${cases} to ${cases + 20}`, upd(t, { fields: { evalCases: cases + 20 } })));
    out.push(ask("Change the trigger", `Change the trigger of ${t.name} to "…"`));
  }
  if (t.kind === "agent") {
    const order = ["trainee", "supervised", "autonomous"];
    const i = order.indexOf(String(f.autonomy));
    if (i < 2 && dir !== "stricter") out.push(sug(`Promote to ${order[i + 1]}`, upd(t, { fields: { autonomy: order[i + 1] } }), "primary"));
    if (i > 0 && dir !== "looser") out.push(sug(`Move back to ${order[i - 1]}`, upd(t, { fields: { autonomy: order[i - 1] } })));
    out.push(sug(`Limit to ${Math.max(1, Number(f.maxConcurrent ?? 2) - 1)} concurrent tasks`, upd(t, { fields: { maxConcurrent: Math.max(1, Number(f.maxConcurrent ?? 2) - 1) } })));
  }
  if (t.kind === "scheduler") {
    const cron = String(f.cron ?? "");
    for (const [label, c] of [["Weekdays at 08:00", "0 8 * * 1-5"], ["Every Monday at 09:00", "0 9 * * 1"], ["Every day at 07:00", "0 7 * * *"]] as const) if (c !== cron) out.push(sug(`Move to ${label.toLowerCase()}`, upd(t, { fields: { cron: c } })));
    out.push(f.enabled === false ? sug("Turn it back on", upd(t, { fields: { enabled: true } }), "primary") : sug("Turn it off", upd(t, { fields: { enabled: false } })));
  }
  if (t.kind === "template") {
    out.push(ask("Add a field", `Add field "…" to ${t.name}`));
    for (const c of ["Daily", "Weekly", "Monthly"]) if (c !== f.cadence) out.push(sug(`Make it ${c.toLowerCase()}`, upd(t, { fields: { cadence: c } })));
  }
  if (t.kind === "sensor") {
    const days = Number(f.retentionDays ?? 365);
    if (dir !== "looser") out.push(sug(`Keep data for ${Math.max(30, Math.round(days / 2))} days instead of ${days}`, upd(t, { fields: { retentionDays: Math.max(30, Math.round(days / 2)) } }), "primary"));
    if (f.health !== "ok") out.push(sug("Mark it healthy after reconnecting", upd(t, { fields: { health: "ok" } })));
  }
  if (t.kind === "tool") {
    const rl = Number(f.rateLimitPerMin ?? 60);
    out.push(sug(`Lower the rate limit to ${Math.max(5, Math.round(rl / 2))} per minute`, upd(t, { fields: { rateLimitPerMin: Math.max(5, Math.round(rl / 2)) } })));
    out.push(sug(`Raise the rate limit to ${rl * 2} per minute`, upd(t, { fields: { rateLimitPerMin: rl * 2 } })));
  }
  if (t.kind === "loop") {
    for (const c of ["Daily", "Weekly", "Monthly"]) if (c !== f.reviewCadence) out.push(sug(`Review it ${c.toLowerCase()}`, upd(t, { fields: { reviewCadence: c } })));
  }
  const better = describe(d, t);
  if (better && better !== t.description) out.push(sug("Rewrite the description from its settings", upd(t, { description: better })));
  const ideas = topicIdeas(t);
  if (ideas.length) out.push(sug(`Add topics: ${ideas.join(", ")}`, upd(t, { topics: [...t.topics, ...ideas] })));
  return out.filter((x, i, all) => all.findIndex((y) => JSON.stringify(y.input ?? y.prompt) === JSON.stringify(x.input ?? x.prompt)) === i).slice(0, 6);
}

// ---------------------------------------------------------------- replies

type Ctx = { d: TenantData; h: Human; wf: Workflow; req: ChatRequest; raw: string; text: string };

function base(partial: Partial<ChatReply>): ChatReply {
  return { answer: "", bullets: [], cards: [], suggestions: [], proposal: null, focus: null, workflowId: null, ...partial };
}

function propose(c: Ctx, input: ProposalInput, lead: string, alt: Suggestion[] = []): ChatReply {
  let p: Proposal;
  try {
    p = review(c.d, c.h, input);
  } catch (e) {
    const msg = e instanceof StudioError ? e.message : "I could not build that change.";
    const t = input.targetId ? itemOf(c.d.studio, input.targetId) ?? workflowOf(c.d.studio, input.targetId) : null;
    return base({ answer: msg, suggestions: t ? guidance(c.d, t) : [], focus: t ? { kind: input.kind, id: t.id } : null });
  }
  const t = input.targetId ? itemOf(c.d.studio, input.targetId) ?? workflowOf(c.d.studio, input.targetId) : null;
  const cards = t ? historyCards(c.d, t) : membersOf(c.d.studio, c.wf).filter((m) => m.kind === input.kind).slice(0, 3).map((m) => itemCard(m));
  const rv = p.review;
  const route = rv.authority.route === "apply" ? "You can confirm it yourself." : rv.authority.route === "approval" ? `It goes to ${rv.authority.approver} for approval.` : rv.authority.reason;
  return base({
    answer: `${lead} The ${REVIEWER} rates it ${rv.verdict} at C${rv.criticality}. ${route}`,
    bullets: input.intent === "delete"
      ? rv.affected.slice(1, 7).map((a) => `${a.name}: ${a.how}`).concat(rv.affected.length < 2 ? ["Nothing else points at it."] : [])
      : p.changes.filter((ch) => input.intent !== "create" || ch.after).slice(0, 6).map((ch) => (input.intent === "create" ? `${ch.label}: ${ch.after}` : `${ch.label}: ${ch.before ?? "empty"} → ${ch.after ?? "empty"}`)),
    cards, proposal: p, focus: t ? { kind: input.kind, id: t.id } : null,
    suggestions: [...rv.fixes, ...alt, ...(t && input.intent === "update" ? guidance(c.d, t).filter((g) => JSON.stringify(g.input?.patch) !== JSON.stringify(input.patch)) : [])].filter((x, i, all) => all.findIndex((y) => y.label === x.label || (!!x.input && JSON.stringify(y.input) === JSON.stringify(x.input))) === i).slice(0, 5),
  });
}

function overview(c: Ctx): ChatReply {
  const s = c.d.studio;
  const ms = membersOf(s, c.wf);
  const hc = healthOf(c.d, c.wf);
  const breaks = hc.findings.filter((f) => f.severity === "break");
  return base({
    answer: `${c.wf.name}: ${describe(c.d, c.wf)}${breaks.length ? ` ${breaks.length} thing${breaks.length > 1 ? "s are" : " is"} broken right now.` : " Nothing is broken right now."}`,
    bullets: MEMBER_ORDER.map((k) => [k, ms.filter((m) => m.kind === k)] as const).filter(([, l]) => l.length).map(([k, l]) => `${KIND_PLURAL[k]}: ${l.map((m) => m.name).join(", ")}`),
    cards: [itemCard(c.wf), ...ms.filter((m) => m.kind === "skill" || m.kind === "policy").slice(0, 3).map((m) => itemCard(m))],
    focus: { kind: "workflow", id: c.wf.id },
    suggestions: [...(breaks.length ? [ask("Show me what is broken and how to fix it", "What is broken in this workflow?")] : []), ask("Make a policy stricter", "Make the refund policy stricter"), ask("Add a scheduler", "Add a scheduler that runs every Monday at 9"), ask("Which tools are shared?"), ...guidance(c.d, c.wf).slice(0, 2)].slice(0, 5),
  });
}

function help(c: Ctx): ChatReply {
  return base({
    answer: `I edit ${c.wf.name} with you. Describe what you want in your own words; I find the right part, suggest concrete options, and the ${REVIEWER} checks every change against the whole workflow before anyone confirms it.`,
    bullets: [
      "Change things: \"make refunds stricter\", \"move the weekly report to Fridays at 4pm\", \"promote the refund agent\"",
      "Create things: \"add a policy that caps goodwill credits at 2,000\", \"add a scheduler for the receivables chase every weekday at 8\"",
      "Delete things: \"delete the expense capture skill\" (I show what would break first)",
      "Wire things: \"add tool crm.update to lead qualification\", \"remove pii masking from answer product question\"",
      "Ask: \"what changed in the refund window?\", \"which tools are shared?\", \"what is broken?\", \"who can approve this?\"",
      "Descriptions and topics too: \"rewrite the description\", \"add topic churn\"",
    ],
    suggestions: [ask("What is broken in this workflow?"), ask("Show the history of the main policy", `What changed in ${membersOf(c.d.studio, c.wf).find((m) => m.kind === "policy")?.name ?? "the policy"}?`), ask("Which tools are shared?")],
    focus: { kind: "workflow", id: c.wf.id },
  });
}

function healthReply(c: Ctx): ChatReply {
  const hc = healthOf(c.d, c.wf);
  const breaks = hc.findings.filter((f) => f.severity === "break");
  const warns = hc.findings.filter((f) => f.severity === "warn");
  const refs = [...breaks, ...warns].map((f) => f.ref).filter((r): r is NonNullable<typeof r> => !!r);
  const cardIds = [...new Set(refs.map((r) => r.id))].slice(0, 4);
  return base({
    answer: breaks.length
      ? `The ${REVIEWER} found ${breaks.length} break${breaks.length > 1 ? "s" : ""} and ${warns.length} warning${warns.length === 1 ? "" : "s"} in ${c.wf.name}. Each fix below is reviewed again before it applies.`
      : warns.length ? `Nothing in ${c.wf.name} is broken. There ${warns.length === 1 ? "is 1 thing" : `are ${warns.length} things`} worth tightening.` : `${c.wf.name} is healthy. Every skill has an agent, its tools and the capabilities it needs.`,
    bullets: [...breaks, ...warns].slice(0, 8).map((f) => `${f.severity === "break" ? "Breaks" : "Watch"}: ${f.text}`),
    cards: cardIds.map((id) => itemOf(c.d.studio, id)).filter((x): x is StudioItem => !!x).map((x) => itemCard(x)),
    suggestions: hc.fixes.length ? hc.fixes.slice(0, 5) : guidance(c.d, c.wf).slice(0, 3),
    focus: { kind: "workflow", id: c.wf.id },
  });
}

function historyReply(c: Ctx, t: StudioItem | Workflow): ChatReply {
  const revs = historyOf(c.d, t.id);
  const last = revs[0];
  return base({
    answer: last ? `${t.name} is at v${t.version}. The last change was "${last.summary}" by ${nameOfPerson(c.d, last.by)}. ${revs.length} version${revs.length === 1 ? "" : "s"} on record; the panel on the right lists them all.` : `${t.name} has no recorded history yet.`,
    bullets: revs.slice(0, 5).map((r) => `v${r.version} · ${r.at.slice(0, 10)} · ${r.summary}`),
    cards: historyCards(c.d, t),
    suggestions: [...guidance(c.d, t).slice(0, 3), ask(`Who depends on ${t.name}?`)],
    focus: { kind: "members" in t ? "workflow" : t.kind, id: t.id },
  });
}

function nameOfPerson(d: TenantData, id: string) {
  return d.humans.find((h) => h.id === id)?.name ?? id;
}

function explain(c: Ctx, t: StudioItem | Workflow): ChatReply {
  if ("members" in t) return overview(c);
  const s = c.d.studio;
  const related = [
    ...refsOf(t.kind, t.fields).map((r) => itemOf(s, r.id)),
    ...scopeOf(s, c.wf).filter((x) => refsOf(x.kind, x.fields).some((r) => r.id === t.id)),
  ].filter((x): x is StudioItem => !!x);
  const shared = t.kind === "tool" ? workflowsUsingTool(s, t.id) : [];
  return base({
    answer: `${t.name} (${KIND_LABEL[t.kind].toLowerCase()}, v${t.version}, ${t.status}). ${describe(c.d, t)}${shared.length > 1 ? ` It is shared by ${shared.length} workflows: ${shared.map((w) => w.name).join(", ")}.` : ""}`,
    bullets: readableFields(c.d, t).slice(0, 8),
    cards: [itemCard(t), ...[...new Map(related.map((r) => [r.id, r])).values()].slice(0, 3).map((r) => itemCard(r))],
    suggestions: [...guidance(c.d, t).slice(0, 4), ask(`What changed in ${t.name}?`)],
    focus: { kind: t.kind, id: t.id },
  });
}

function listKind(c: Ctx, kind: StudioKind): ChatReply {
  if (kind === "workflow") {
    const all = c.d.studio.workflows;
    return base({ answer: `${all.length} workflows. Each owns its skills, agents, policies, templates, sensors, schedulers and loops; only tools are shared.`, bullets: all.map((w) => `${w.name} · ${w.members.length} parts · DRI ${nameOfPerson(c.d, w.dri)}`), cards: all.slice(0, 4).map((w) => itemCard(w)), suggestions: all.filter((w) => w.id !== c.wf.id).slice(0, 3).map((w) => ask(`Open ${w.name}`, `Switch to ${w.name}`)) });
  }
  const list = kind === "tool" ? scopeOf(c.d.studio, c.wf).filter((x) => x.kind === "tool") : membersOf(c.d.studio, c.wf).filter((m) => m.kind === kind);
  return base({
    answer: list.length ? `${c.wf.name} has ${list.length} ${KIND_PLURAL[kind].toLowerCase()}.${kind === "tool" ? " Tools are shared, so a change to one reaches every workflow that uses it." : ""}` : `${c.wf.name} has no ${KIND_PLURAL[kind].toLowerCase()} yet.`,
    bullets: list.map((x) => (kind === "tool" ? `${x.name} · used by ${workflowsUsingTool(c.d.studio, x.id).length} workflow(s)` : `${x.name} · v${x.version} · ${x.status}`)),
    cards: list.slice(0, 4).map((x) => itemCard(x)),
    suggestions: [ask(`Add a ${KIND_LABEL[kind].toLowerCase()}`, `Add a new ${KIND_LABEL[kind].toLowerCase()} called "…"`), ...list.slice(0, 2).map((x) => ask(`Tell me about ${x.name}`))],
    focus: list[0] ? { kind, id: list[0].id } : null,
  });
}

function sharedTools(c: Ctx): ChatReply {
  const tools = scopeOf(c.d.studio, c.wf).filter((x) => x.kind === "tool");
  const rows = tools.map((t) => ({ t, ws: workflowsUsingTool(c.d.studio, t.id) })).sort((a, b) => b.ws.length - a.ws.length);
  return base({
    answer: `${c.wf.name} uses ${tools.length} tool${tools.length === 1 ? "" : "s"}. ${rows.filter((r) => r.ws.length > 1).length} of them are shared with other workflows, so changing them is reviewed across every workflow that uses them.`,
    bullets: rows.map((r) => `${r.t.name}: ${r.ws.map((w) => w.name).join(", ")}`),
    cards: rows.slice(0, 4).map((r) => itemCard(r.t)),
    suggestions: rows.slice(0, 2).map((r) => ask(`What happens if I change ${r.t.name}?`, `Lower the rate limit of ${r.t.name}`)),
  });
}

function authorityReply(c: Ctx): ChatReply {
  const dri = nameOfPerson(c.d, c.wf.dri);
  const eds = c.wf.editors.map((e) => nameOfPerson(c.d, e));
  return base({
    answer: `${dri} is the DRI of ${c.wf.name}${eds.length ? `, with ${eds.join(" and ")} as editors` : ""}. You are ${c.h.name} (${c.h.tier}, approves up to C${c.h.maxApprovalCriticality}).`,
    bullets: [
      "C0 and C1 edits (topics, wording, timing) are logged and apply at once for L1 and L2.",
      "C2 edits apply at once for the DRI, editors and L1; anyone else sends them to the DRI.",
      "C3 needs an L1 DRI; C4 needs two L1 approvers. Nobody approves their own change.",
      `Anything the ${REVIEWER} marks breaking always goes to a second person.`,
      "L3 can view and suggest, never change.",
    ],
    focus: { kind: "workflow", id: c.wf.id },
  });
}

// ---------------------------------------------------------------- intents

function createIntent(c: Ctx): ChatReply {
  const { text, raw } = c;
  const kind = (kindIn(text.replace(/\b(add|create|new|set up|introduce)\b/, "")) ?? kindIn(text)) as StudioKind | null;
  if (!kind) {
    return base({ answer: "What should I add? Pick a kind and describe it in a sentence; I fill in sensible defaults and show you the review before anything changes.", suggestions: MEMBER_ORDER.map((k) => ask(`Add a ${KIND_LABEL[k].toLowerCase()}`, `Add a new ${KIND_LABEL[k].toLowerCase()} called "…"`)).slice(0, 6) });
  }
  const name =
    quoted(raw) ??
    raw.match(/\b(?:called|named|titled)\s+(.+?)(?=\s+(?:that|which|to|for|every|with|at|when|on)\b|[.,]|$)/i)?.[1] ??
    raw.match(new RegExp(`\\b(?:${KIND_SYNONYMS[kind].join("|")})\\s+(?:for|to)\\s+(.+?)(?=\\s+(?:that|which|every|with|at|when|on)\\b|[.,]|$)`, "i"))?.[1] ?? null;
  const fields: ItemFields = {};
  const extra: Suggestion[] = [];
  let finalName = name ? cap(name.trim()) : "";
  if (kind === "workflow") {
    if (!finalName) return base({ answer: "What is the new workflow called, and what does it do?", suggestions: [ask("Create workflow \"Churn prevention\"", "Create a new workflow called \"Churn prevention\" that reaches out to accounts at risk")] });
    const desc = raw.match(/\b(?:that|which|to)\s+(.+)$/i)?.[1] ?? "";
    return propose(c, { intent: "create", kind, targetId: null, workflowId: null, patch: { name: finalName, description: desc ? cap(desc) : "", topics: tokens(finalName).slice(0, 2) } }, `Here is a draft for a new workflow, ${finalName}. Add skills, agents and policies to it once it exists.`);
  }
  const member = kind as MemberKind;
  const scope = scopeOf(c.d.studio, c.wf);
  const agents = scope.filter((x) => x.kind === "agent" && x.status === "active");
  const skillsIn = scope.filter((x) => x.kind === "skill");
  if (member === "scheduler") {
    const cron = cronIn(text);
    const target = resolve(c.d, c.wf, text, null, "skill", "skill").target?.item ?? null;
    if (cron) fields.cron = cron;
    if (target) {
      fields.target = target.id;
      fields.agent = ((target.fields.agents as string[]) ?? [])[0] ?? "";
    }
    fields.timezone = c.d.tenant.timezone;
    fields.enabled = true;
    if (!finalName) finalName = target ? `Run ${target.name.toLowerCase()}` : "New schedule";
    if (!target) {
      return base({
        answer: `Which skill should the new scheduler run${cron ? ` (${describeCron(cron).toLowerCase()})` : ""}? Pick one:`,
        suggestions: skillsIn.slice(0, 5).map((sk) => sug(sk.name, { intent: "create", kind: "scheduler", targetId: null, workflowId: c.wf.id, patch: { name: `Run ${sk.name.toLowerCase()}`, description: `Wakes ${sk.name} on schedule.`, topics: ["schedule"], fields: { cron: cron ?? "0 9 * * 1", timezone: c.d.tenant.timezone, target: sk.id, agent: ((sk.fields.agents as string[]) ?? [])[0] ?? "", enabled: true, catchUp: false } } }, "primary")),
      });
    }
    if (!cron) {
      fields.cron = "0 9 * * 1";
      extra.push(...[["Weekdays at 08:00", "0 8 * * 1-5"], ["Every day at 07:00", "0 7 * * *"], ["Hourly", "0 * * * *"]].map(([l, cr]) => sug(`Run it ${l.toLowerCase()} instead`, { intent: "create", kind: "scheduler", targetId: null, workflowId: c.wf.id, patch: { name: finalName, topics: ["schedule"], fields: { ...fields, cron: cr } } })));
    }
    return propose(c, { intent: "create", kind: member, targetId: null, workflowId: c.wf.id, patch: { name: finalName, description: `${describeCron(String(fields.cron))}, wakes ${target.name}.`, topics: ["schedule"], fields } }, `Drafted a scheduler: ${describeCron(String(fields.cron)).toLowerCase()} it runs ${target.name}.${cron ? "" : " You did not say when, so I picked Mondays at 09:00."}`, extra);
  }
  if (member === "skill") {
    const named = resolve(c.d, c.wf, text, null, "agent", "agent").target?.item ?? null;
    const agent = named ?? agents[0];
    const trig = raw.match(/\bwhen\s+(.+?)(?=[.,]|$)/i)?.[1];
    Object.assign(fields, { trigger: trig ? cap(trig) : "Describe when this skill starts", steps: ["retrieval: Retrieve the facts it needs", "judgment: Decide what to do", "quality_gate: Check against policy before acting"], agents: agent ? [agent.id] : [], tools: [], policies: [], templates: [], inputs: [], outputs: ["Result"], evalCases: 0 });
    if (!finalName) finalName = trig ? `Handle ${trig}` : "New skill";
    const pol = scope.filter((x) => x.kind === "policy").slice(0, 2);
    return propose(c, { intent: "create", kind: member, targetId: null, workflowId: c.wf.id, patch: { name: finalName, description: trig ? `Runs when ${trig}.` : "", topics: c.wf.topics.slice(0, 1), fields } }, `Drafted a skill with a safe three step shape${agent ? `, run by ${agent.name}` : ""}. It has no tools or policy yet; the review shows what to add.`, pol.map((p) => sug(`Also govern it by ${p.name}`, { intent: "create", kind: "skill", targetId: null, workflowId: c.wf.id, patch: { name: finalName, topics: c.wf.topics.slice(0, 1), fields: { ...fields, policies: [p.id] } } })));
  }
  if (member === "policy") {
    const stmt = raw.match(/\b(?:that|which|saying|so that)\s+(.+)$/i)?.[1];
    const n = numberIn(text);
    Object.assign(fields, { statement: stmt ? cap(stmt) : "State the rule in one sentence", ruleKind: /\bdays?\b/.test(text) ? "max_days" : n !== null ? "max_amount_minor" : "statement", criticality: String(c.wf.criticality), validFrom: new Date().toISOString().slice(0, 10) });
    if (n !== null) fields[/\bdays?\b/.test(text) ? "param.days" : "param.amountMinor"] = /\bdays?\b/.test(text) ? n : Math.round(n * 100);
    if (!finalName) finalName = stmt ? cap(tokens(stmt).slice(0, 3).join(" ")) : "New policy";
    return propose(c, { intent: "create", kind: member, targetId: null, workflowId: c.wf.id, patch: { name: finalName, description: fields.statement as string, topics: c.wf.topics.slice(0, 1), fields } }, `Drafted a policy${n !== null ? ` with a limit of ${/\bdays?\b/.test(text) ? `${n} days` : money(Math.round(n * 100), c.d.tenant.currency)}` : ""}. Attach it to a skill afterwards so it governs something.`);
  }
  if (member === "template") {
    const list = raw.match(/\bfields?\s+(.+?)(?=[.]|$)/i)?.[1];
    Object.assign(fields, { cadence: /\bdaily\b/.test(text) ? "Daily" : /\bmonthly\b/.test(text) ? "Monthly" : "Weekly", fieldList: list ? list.split(/,|\band\b/).map((x) => cap(x.trim())).filter(Boolean) : ["Count", "Notes"], freshnessRule: "Required fields fresh within 24 hours", requiredEvidence: [], sensors: [] });
    if (!finalName) finalName = "New report";
  }
  if (member === "sensor") {
    Object.assign(fields, { source: raw.match(/\bfrom\s+(.+?)(?=[.,]|$)/i)?.[1] ?? "Describe the source", events: [], feeds: agents.slice(0, 1).map((a) => a.id), retentionDays: 365, personalData: /\b(personal|pii|customer data)\b/.test(text), health: "ok", sensorKind: "monitor" });
    if (!finalName) finalName = "New sensor";
  }
  if (member === "agent") {
    Object.assign(fields, { autonomy: "trainee", capabilities: [], accessLevel: "internal", model: "claude-sonnet-5-5", maxConcurrent: 2 });
    if (!finalName) finalName = "New agent";
  }
  if (member === "tool") {
    const label = raw.match(/\b([a-z]+(?:[._-][a-z]+)+)\b/)?.[1];
    if (!finalName) finalName = label ?? "new.tool";
    Object.assign(fields, { endpoint: `https://api.internal/${finalName.replace(/\./g, "/")}`, capability: raw.match(/\bneeds?\s+([a-z]+:[a-z]+)/i)?.[1] ?? `${finalName.split(".")[0]}:use`, sensitivity: "internal", sideEffect: /\b(refund|charge|pay|credit)\b/.test(text) ? "money" : /\b(post|publish|reply)\b/.test(text) ? "public" : "write", rateLimitPerMin: 60 });
    return propose(c, { intent: "create", kind: member, targetId: null, workflowId: null, patch: { name: finalName, description: `Shared tool ${finalName}.`, topics: [finalName.split(".")[0]], fields } }, `Drafted a shared tool, ${finalName}. Tools live outside any workflow, so every workflow can use it once it exists.`);
  }
  if (member === "loop") {
    Object.assign(fields, { signal: scope.filter((x) => x.kind === "sensor").slice(0, 2).map((x) => x.id), guards: scope.filter((x) => x.kind === "policy").slice(0, 1).map((x) => x.id), actions: [], gate: "Quality gate", learning: scope.find((x) => x.kind === "template")?.id ?? "", reviewCadence: "Weekly" });
    if (!finalName) finalName = `${c.wf.name} improvement loop`;
  }
  return propose(c, { intent: "create", kind: member, targetId: null, workflowId: c.wf.id, patch: { name: finalName, description: "", topics: c.wf.topics.slice(0, 1), fields } }, `Drafted a new ${KIND_LABEL[member].toLowerCase()}, ${finalName}, with defaults you can change before confirming.`);
}

function refIntent(c: Ctx, adding: boolean): ChatReply | null {
  const m = adding
    ? c.raw.match(/\b(?:add|attach|use|assign|link|connect|give|grant)\s+(.+?)\s+(?:to|in|on|for|into)\s+(.+?)[.?!]?$/i)
    : c.raw.match(/\b(?:remove|detach|unassign|unlink|drop|disconnect|take|revoke)\s+(.+?)\s+(?:from|off|out of)\s+(.+?)[.?!]?$/i);
  if (!m) return null;
  const a = m[1].toLowerCase();
  const b = m[2].toLowerCase();
  const container = resolve(c.d, c.wf, b, c.req.focus, kindIn(b)).target;
  if (!container?.item) return null;
  const host = container.item;
  const specs = FIELD_SPECS[host.kind].filter((f) => (f.type === "refs" || f.type === "ref") && f.ref);
  // Capabilities and list entries are plain strings, not items.
  const listField = host.kind === "agent" && /\b[a-z]+:[a-z]+\b/.test(a) ? "capabilities" : /\btopics?\b/.test(a) ? "topics" : null;
  if (listField === "capabilities") {
    const capName = a.match(/\b([a-z]+:[a-z]+)\b/)![1];
    const cur = (host.fields.capabilities as string[]) ?? [];
    if (adding === cur.includes(capName)) return base({ answer: `${host.name} ${adding ? "already holds" : "does not hold"} ${capName}.`, cards: [itemCard(host)], focus: { kind: host.kind, id: host.id } });
    const next = adding ? [...new Set([...cur, capName])] : cur.filter((x) => x !== capName);
    return propose(c, upd(host, { fields: { capabilities: next } }), `${adding ? "Granting" : "Revoking"} ${capName} ${adding ? "to" : "from"} ${host.name}.`);
  }
  let picked: { spec: FieldSpec; item: StudioItem } | null = null;
  for (const spec of specs) {
    const hit = resolve(c.d, c.wf, a, null, spec.ref!, spec.ref!).target?.item;
    if (hit && (!picked || kindIn(a) === spec.ref)) picked = { spec, item: hit };
  }
  if (!picked) return null;
  const cur = host.fields[picked.spec.key];
  if (picked.spec.type === "ref") return propose(c, upd(host, { fields: { [picked.spec.key]: adding ? picked.item.id : "" } }), `${host.name} will ${adding ? `use ${picked.item.name}` : `stop using ${picked.item.name}`} for ${picked.spec.label.toLowerCase()}.`);
  const list = Array.isArray(cur) ? cur : [];
  if (adding === list.includes(picked.item.id)) {
    return base({ answer: `${host.name} ${adding ? "already" : "does not"} ${picked.spec.rel ?? "use"} ${picked.item.name}. Nothing to change.`, cards: [itemCard(host), itemCard(picked.item)], suggestions: guidance(c.d, host).slice(0, 4), focus: { kind: host.kind, id: host.id } });
  }
  const next = adding ? [...new Set([...list, picked.item.id])] : list.filter((x) => x !== picked!.item.id);
  return propose(c, upd(host, { fields: { [picked.spec.key]: next } }), `${adding ? "Adding" : "Removing"} ${picked.item.name} ${adding ? "to" : "from"} ${host.name} (${picked.spec.label.toLowerCase()}).`);
}

function updateIntent(c: Ctx): ChatReply {
  const { text, raw, d, wf, req } = c;
  const kindHint = kindIn(text);
  const { target, ambiguous } = resolve(d, wf, text, req.focus, kindHint);
  const dir0 = directionIn(text);
  if (ambiguous.length && dir0 && ambiguous.every((a) => a.t.kind === "policy")) {
    const items = ambiguous.map((a) => a.t.item!).filter(Boolean);
    return base({
      answer: `${items.length} policies match. Here are concrete ${dir0} options for each; pick one and the ${REVIEWER} checks it against the whole workflow.`,
      cards: items.map((i) => itemCard(i)),
      suggestions: items.flatMap((i) => guidance(d, i, dir0).filter((g) => g.input?.patch.fields).slice(0, 2).map((g) => ({ ...g, label: `${i.name}: ${g.label}` }))).slice(0, 6),
      focus: { kind: "policy", id: items[0].id },
    });
  }
  if (ambiguous.length) {
    return base({ answer: `I found ${ambiguous.length} close matches. Which one do you mean?`, cards: ambiguous.map((a) => itemCard(a.t.item ?? a.t.wf!)), suggestions: ambiguous.map((a) => ask(a.t.name, `${raw} (${a.t.name})`.replace(/\s+\(.*\)\s+\(/, " ("))) });
  }
  if (!target && /\b(description|describe|summary|purpose|topics?|tags?|rename)\b/.test(text)) {
    const f = req.focus ? (req.focus.kind === "workflow" ? workflowOf(d.studio, req.focus.id) : itemOf(d.studio, req.focus.id)) : null;
    return updateIntent({ ...c, req: { ...req, focus: { kind: f && !("members" in f) ? f.kind : "workflow", id: f?.id ?? wf.id } }, text: `${text} it` });
  }
  if (!target) {
    const kind = kindHint && kindHint !== "workflow" ? (kindHint as MemberKind) : null;
    const list = kind ? membersOf(d.studio, wf).filter((m) => m.kind === kind) : [];
    if (kind === "tool") list.push(...scopeOf(d.studio, wf).filter((x) => x.kind === "tool"));
    return base({
      answer: kind ? `Which ${KIND_LABEL[kind].toLowerCase()} in ${wf.name} should change?` : `What should I change in ${wf.name}? Name the part, or pick one below.`,
      cards: list.slice(0, 4).map((x) => itemCard(x)),
      suggestions: (list.length ? list : membersOf(d.studio, wf)).slice(0, 5).map((x) => ask(x.name, `${raw.replace(/[.?!]$/, "")} for ${x.name}`)),
    });
  }
  const t = target.item ?? target.wf!;
  const kind = target.kind;
  const dir = directionIn(text);
  const timeWords = /\b(at \d|\d\s*(am|pm)|\d:\d\d|daily|weekly|monthly|hourly|every|weekdays?|mondays?|tuesdays?|wednesdays?|thursdays?|fridays?|saturdays?|sundays?|morning|evening|nightly)\b/.test(text);
  if (timeWords && kind !== "scheduler" && /\b(move|reschedule|run|schedule|shift|change)\b/.test(text)) {
    const fillers = new Set(kind === "template" ? membersOf(d.studio, wf).filter((m) => m.kind === "skill" && ((m.fields.templates as string[]) ?? []).includes(t.id)).map((m) => m.id) : [t.id]);
    const sch = membersOf(d.studio, wf).find((m) => m.kind === "scheduler" && (fillers.has(String(m.fields.target)) || m.name.toLowerCase().includes(t.name.toLowerCase())));
    const cron = cronIn(text);
    if (sch && cron) return propose(c, upd(sch, { fields: { cron } }), `${t.name} runs on the scheduler "${sch.name}". Moving it to ${describeCron(cron).toLowerCase()}.`);
  }

  // Status words
  const status = /\b(pause|suspend|hold)\b/.test(text) ? "paused" : /\b(resume|unpause|activate|reactivate)\b/.test(text) ? "active" : /\b(retire|archive|deprecate)\b/.test(text) ? "retired" : null;
  if (status && !(kind === "scheduler" && /\b(enable|disable|turn)\b/.test(text))) return propose(c, upd(t, { status }), `Setting ${t.name} to ${status}.`);

  // Rename
  const rn = raw.match(/\brename\b.*?\bto\s+(.+?)[.?!]?$/i);
  if (rn) return propose(c, upd(t, { name: cap(rn[1].replace(/^["']|["']$/g, "")) }), `Renaming ${t.name}.`);

  // Topics
  if (/\b(topics?|tags?)\b/.test(text)) {
    const replacing = /\b(set|replace|only)\b/.test(text);
    const after = raw.match(/\b(?:topics?|tags?)\s+(.+)$/i)?.[1] ?? "";
    const value = replacing ? raw.match(/\bto\s+(.+)$/i)?.[1] ?? after : quoted(raw) ?? after.replace(/\s+(?:to|on|for|from|in|of|onto)\s+.*$/i, "");
    const vals = value.split(/,|\band\b/).map((v) => v.trim().toLowerCase().replace(/^(topic|tag)s?\s+/, "")).filter((v) => v && !STOP.has(v));
    if (/\b(remove|drop|delete|untag)\b/.test(text)) {
      const next = t.topics.filter((x) => !vals.includes(x));
      return propose(c, upd(t, { topics: next }), `Removing topic${vals.length > 1 ? "s" : ""} ${vals.join(", ")} from ${t.name}.`);
    }
    if (vals.length && replacing) return propose(c, upd(t, { topics: vals }), `Replacing the topics of ${t.name}.`);
    if (vals.length) return propose(c, upd(t, { topics: [...new Set([...t.topics, ...vals])] }), `Adding topic${vals.length > 1 ? "s" : ""} ${vals.join(", ")} to ${t.name}.`);
    const ideas = topicIdeas(t);
    return base({ answer: `${t.name} has topics: ${t.topics.join(", ") || "none"}. What should I add?`, suggestions: ideas.length ? [sug(`Add ${ideas.join(", ")}`, upd(t, { topics: [...t.topics, ...ideas] }), "primary")] : [], focus: { kind, id: t.id } });
  }

  // Description
  if (/\b(description|describe|summary|purpose)\b/.test(text)) {
    const value = quoted(raw) ?? raw.match(/\b(?:description|describe it|summary)\b.*?\b(?:to|as|:)\s+(.+)$/i)?.[1];
    if (value) return propose(c, upd(t, { description: cap(value.trim()) }), `Updating the description of ${t.name}.`);
    const generated = describe(d, t);
    return propose(c, upd(t, { description: generated }), `Here is a description written from what ${t.name} actually does. Edit it before confirming if you want different wording.`, [ask("Write my own wording", `Change the description of ${t.name} to "…"`)]);
  }

  const item = target.item;
  const field = fieldIn(kind, text, item);
  // "Make X stricter" about a skill, agent or the workflow: the limits live in the policies that govern it.
  if (dir && !field && kind !== "policy") {
    const scope = membersOf(d.studio, wf);
    const skills = kind === "skill" ? [item!] : kind === "agent" ? scope.filter((m) => m.kind === "skill" && ((m.fields.agents as string[]) ?? []).includes(t.id)) : kind === "workflow" ? scope.filter((m) => m.kind === "skill") : [];
    const governing = [...new Set(skills.flatMap((sk) => (sk.fields.policies as string[]) ?? []))].map((id) => itemOf(d.studio, id)).filter((p): p is StudioItem => !!p && Object.entries(p.fields).some(([k, v]) => isParam(k) && typeof v === "number"));
    if (governing.length) {
      const opts = governing.flatMap((p) => guidance(d, p, dir).filter((g) => g.input?.patch.fields && Object.keys(g.input.patch.fields).some(isParam)).map((g) => (governing.length > 1 ? { ...g, label: `${p.name}: ${g.label}` } : g)));
      if (opts[0]?.input) return propose(c, opts[0].input, `${t.name} is limited by ${governing.map((p) => p.name).join(" and ")}. To make it ${dir}, I would change the limit there.`, opts.slice(1));
    }
  }
  // Policies with a direction but no exact value: propose the first concrete option and offer the rest.
  if (item && (!field || isParam(field)) && dir && item.kind === "policy") {
    const opts = guidance(d, item, dir).filter((g) => g.input && g.input.patch.fields && Object.keys(g.input.patch.fields).some((k) => isParam(k) && (!field || k === field)));
    const n = numberIn(text);
    if (field && n !== null) {
      const v = paramName(field) === "amountMinor" ? Math.round(n * 100) : n;
      return propose(c, upd(item, { fields: { [field]: v } }), `Changing ${fieldLabel("policy", field).toLowerCase()} of ${item.name}.`);
    }
    if (opts[0]?.input) return propose(c, opts[0].input, `To make ${item.name} ${dir}, I would start here. Other options are below.`, opts.slice(1));
  }
  if (!field && item && (item.kind === "scheduler") && cronIn(text)) {
    return propose(c, upd(item, { fields: { cron: cronIn(text)! } }), `Moving ${item.name} to ${describeCron(cronIn(text)!).toLowerCase()}.`);
  }
  if (!field) {
    return base({
      answer: `Here is what I can change on ${t.name}. Pick one, or say it in your own words; you do not need exact field names.`,
      bullets: item ? readableFields(d, item).slice(0, 6) : [`Description: ${t.description}`, `Topics: ${t.topics.join(", ")}`],
      cards: historyCards(d, t, 3),
      suggestions: guidance(d, t, dir),
      focus: { kind, id: t.id },
    });
  }

  // A field was named: work out the value.
  if (["name", "description", "topics", "status", "dri"].includes(field)) {
    const v = afterTo(raw);
    if (!v) return base({ answer: `What should the ${fieldLabel(kind, field).toLowerCase()} of ${t.name} be?`, suggestions: guidance(d, t), focus: { kind, id: t.id } });
    if (field === "dri") {
      const person = d.humans.find((h) => v.toLowerCase().includes(h.name.toLowerCase().split(" ")[0]));
      if (!person) return base({ answer: `Who should own ${t.name}?`, suggestions: d.humans.filter((h) => h.tier !== "L3").slice(0, 5).map((h) => sug(h.name, upd(t, { dri: h.id }))) });
      return propose(c, upd(t, { dri: person.id }), `Making ${person.name} the DRI of ${t.name}.`);
    }
    return propose(c, upd(t, { [field]: field === "topics" ? v.split(/,/).map((x) => x.trim()) : cap(v) } as ProposalInput["patch"]), `Updating the ${fieldLabel(kind, field).toLowerCase()} of ${t.name}.`);
  }
  if (!item) return base({ answer: `Workflows hold a name, description, topics, status and DRI. Which of those should change?`, suggestions: guidance(d, t) });
  if (isParam(field)) {
    const n = numberIn(text);
    const cur = item.fields[field];
    if (typeof cur === "boolean") {
      const b = boolIn(text);
      return b === null ? base({ answer: `Should ${fieldLabel("policy", field).toLowerCase()} be on or off?`, suggestions: guidance(d, item) }) : propose(c, upd(item, { fields: { [field]: b } }), `Turning ${fieldLabel("policy", field).toLowerCase()} ${b ? "on" : "off"}.`);
    }
    if (n === null) return base({ answer: `${fieldLabel("policy", field)} is ${formatValue(cur, paramName(field))} now. What should it become?`, suggestions: guidance(d, item, dir), cards: historyCards(d, item), focus: { kind, id: item.id } });
    const v = paramName(field) === "amountMinor" ? Math.round(n * 100) : n;
    return propose(c, upd(item, { fields: { [field]: v } }), `Changing ${fieldLabel("policy", field).toLowerCase()} of ${item.name}.`);
  }
  const spec = FIELD_SPECS[item.kind].find((f) => f.key === field)!;
  let value: FieldValue | null = null;
  if (spec.key === "cron") value = cronIn(text) ?? afterTo(raw);
  else if (spec.type === "number") value = numberIn(text);
  else if (spec.type === "boolean") value = spec.key === "enabled" && /\b(pause|stop|disable|turn off|off)\b/.test(text) ? false : boolIn(text);
  else if (spec.type === "select") value = spec.options?.find((o) => new RegExp(`\\b${o}\\b`).test(text)) ?? (spec.key === "autonomy" ? (/\bpromote\b/.test(text) ? ["trainee", "supervised", "autonomous"][Math.min(2, ["trainee", "supervised", "autonomous"].indexOf(String(item.fields.autonomy)) + 1)] : /\bdemote\b/.test(text) ? ["trainee", "supervised", "autonomous"][Math.max(0, ["trainee", "supervised", "autonomous"].indexOf(String(item.fields.autonomy)) - 1)] : null) : null);
  else if (spec.type === "list") {
    const v = quoted(raw) ?? afterTo(raw);
    const cur = (item.fields[field] as string[]) ?? [];
    if (v && /\b(add|append|include|insert)\b/.test(text)) value = [...cur, spec.key === "steps" && !/^[a-z_]+:/.test(v) ? `judgment: ${cap(v)}` : cap(v)];
    else if (v && /\b(remove|drop|delete)\b/.test(text)) value = cur.filter((x) => !x.toLowerCase().includes(v.toLowerCase()));
    else if (v) value = v.split(/,|;/).map((x) => x.trim()).filter(Boolean);
  } else if (spec.type === "ref" || spec.type === "refs") {
    const r = refIntent(c, !/\b(remove|detach|unassign)\b/.test(text));
    if (r) return r;
    const hit = resolve(d, wf, text.replace(item.name.toLowerCase(), ""), null, spec.ref!, spec.ref!).target?.item;
    if (hit) value = spec.type === "ref" ? hit.id : [...new Set([...((item.fields[field] as string[]) ?? []), hit.id])];
  } else value = afterTo(raw);
  if (value === null || value === undefined || value === "") {
    return base({ answer: `${spec.label} of ${item.name} is "${formatValue(item.fields[field], field) || "empty"}". What should it become?${spec.hint ? ` (${spec.hint})` : ""}`, suggestions: guidance(d, item, dir), cards: historyCards(d, item, 3), focus: { kind, id: item.id } });
  }
  return propose(c, upd(item, { fields: { [field]: value } }), `Changing ${spec.label.toLowerCase()} of ${item.name}${spec.key === "cron" ? ` to ${describeCron(String(value)).toLowerCase()}` : ""}.`);
}

function deleteIntent(c: Ctx): ChatReply {
  const kindHint = kindIn(c.text);
  const { target, ambiguous } = resolve(c.d, c.wf, c.text, c.req.focus, kindHint);
  if (ambiguous.length) return base({ answer: "Which one should I delete?", cards: ambiguous.map((a) => itemCard(a.t.item ?? a.t.wf!)), suggestions: ambiguous.map((a) => ask(`Delete ${a.t.name}`)) });
  if (!target) return base({ answer: `Which part of ${c.wf.name} should go? Deleting is reviewed like any edit: I show what would break first.`, suggestions: membersOf(c.d.studio, c.wf).slice(0, 5).map((m) => ask(`Delete ${m.name}`)) });
  const t = target.item ?? target.wf!;
  const isWf = target.kind === "workflow";
  return propose(c, { intent: "delete", kind: target.kind, targetId: t.id, workflowId: isWf ? t.id : (t as StudioItem).workflowId ?? c.wf.id, patch: {} }, `Deleting ${t.name}. Read what depends on it before you confirm; retiring keeps the history and is easier to undo.`, [sug(`Retire ${t.name} instead`, upd(t, { status: "retired" }), "primary")]);
}

// ---------------------------------------------------------------- entry points

export function chat(d: TenantData, h: Human, req: ChatRequest): ChatReply {
  const wf = workflowOf(d.studio, req.workflowId) ?? d.studio.workflows[0];
  if (!wf) return base({ answer: "There are no workflows yet. Say \"create a workflow called …\" to start one." });
  const raw = req.message.trim();
  const text = raw.toLowerCase();
  const c: Ctx = { d, h, wf, req, raw, text };
  if (!text || /^(help|\?|what can you do|how does this work|hi|hello|hey)\b/.test(text)) return text.startsWith("h") && !text.startsWith("help") && !text.startsWith("how") ? overview(c) : help(c);
  if (/^(yes|ok|okay|confirm|apply|do it|go ahead|ship it|approve)\b/.test(text)) return base({ answer: "Use Confirm on the proposal card. It shows who has to approve and runs the review once more, so nothing applies from a chat message alone." });

  const sw = text.match(/^(?:switch to|go to|open|jump to|show me)\s+(?:the\s+)?(.+?)(?:\s+workflow)?[.?!]?$/);
  if (sw) {
    const tt = new Set(tokens(sw[1]));
    const best = d.studio.workflows.map((w) => ({ w, sc: score(sw[1], tt, w.name) })).sort((a, b) => b.sc - a.sc)[0];
    if (best && best.sc >= 0.5) {
      const c2 = { ...c, wf: best.w };
      return { ...overview(c2), workflowId: best.w.id, answer: `Switched to ${best.w.name}. ${overview(c2).answer}` };
    }
  }

  if (/\b(shared|share)\b/.test(text) && /\btools?\b/.test(text)) return sharedTools(c);
  if (/\b(who can|who approves|who owns|authority|permission to edit|can i (edit|change))\b/.test(text)) return authorityReply(c);
  if (/\b(broken|break|breaks|health|healthy|issues?|problems?|what'?s wrong|wrong with|fix (it|this|the workflow|everything)|diagnose|check (the )?workflow)\b/.test(text) && !/\b(fix|change)\b.*\bto\b/.test(text)) return healthReply(c);

  const isCreate = /^(please\s+)?(add|create|new|set up|setup|introduce|make a new|make an?|build)\b/.test(text) && !/\b(add|attach|assign|link|use)\s+.+\s+(to|in|on|into)\s+\w/.test(text.replace(/\b(add|create)\s+(a|an|new)\s+/, "")) && !/\btopics?|tags?\b/.test(text);
  if (/^(please\s+)?(delete|remove|drop|get rid of|destroy)\b/.test(text) && !/\s(from|off)\s/.test(text) && !/\btopics?|tags?\b/.test(text)) return deleteIntent(c);
  if (isCreate && kindIn(text)) return createIntent(c);
  if (/^(please\s+)?(add|attach|assign|link|connect|use|give)\b/.test(text) && !/\btopics?|tags?\b/.test(text)) {
    const r = refIntent(c, true);
    if (r) return r;
    if (/\b(add|create)\b/.test(text)) return createIntent(c);
  }
  if (/^(please\s+)?(remove|detach|unassign|unlink|take)\b/.test(text) && !/\btopics?|tags?\b/.test(text)) {
    const r = refIntent(c, false);
    if (r) return r;
  }
  if (/^(please\s+)?(grant|revoke)\b/.test(text)) {
    const r = refIntent(c, text.startsWith("grant") || text.startsWith("please grant"));
    if (r) return r;
  }
  if (/\b(history|versions?|past|previous|changelog|timeline|what changed|changes to|who changed|last change)\b/.test(text)) {
    const { target } = resolve(d, wf, text, req.focus, kindIn(text));
    return historyReply(c, target?.item ?? target?.wf ?? wf);
  }
  const isQuestion = /^(what|which|who|why|how|show|list|tell|explain|describe|where|is|are|does|do|can)\b/.test(text) || text.endsWith("?");
  const isEdit = /\b(change|update|edit|set|rename|make|increase|decrease|raise|lower|reduce|extend|shorten|tighten|loosen|stricter|looser|safer|pause|resume|retire|enable|disable|promote|demote|move|reschedule|replace|rewrite|improve|turn|tag|add|remove|fix|adjust|tweak)\b/.test(text);
  if (isEdit && !(isQuestion && /^(what|which|who|why|how|show|list|tell|explain)\b/.test(text) && !/\b(should|would|can)\b/.test(text))) return updateIntent(c);
  // Questions
  const kind = kindIn(text);
  const { target } = resolve(d, wf, text, req.focus, kind);
  if (target?.item) return explain(c, target.item);
  if (kind && /\b(all|list|which|what)\b/.test(text)) return listKind(c, kind);
  if (kind && !target) return listKind(c, kind);
  return overview(c);
}

/** For forms and one-click suggestions: review an exact input without parsing text. */
export function reviewReply(d: TenantData, h: Human, input: ProposalInput, workflowId: string): ChatReply {
  const wf = workflowOf(d.studio, workflowId) ?? d.studio.workflows[0];
  return propose({ d, h, wf, req: { workflowId, message: "", focus: null, history: [] }, raw: "", text: "" }, input, "Here is that change.");
}
