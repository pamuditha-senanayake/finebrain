// What each kind of studio item holds, in one table that the mock engine, the chat and the forms all read.
import type { FieldValue, MemberKind, StudioKind } from "@/contracts";

export type FieldType = "text" | "longtext" | "number" | "boolean" | "list" | "select" | "refs" | "ref" | "person";

export type FieldSpec = {
  key: string;
  label: string;
  type: FieldType;
  /** For ref and refs: the kind of item the value points to. */
  ref?: MemberKind;
  options?: string[];
  /** Words people use for this field in chat. */
  synonyms?: string[];
  /** How the edge reads on the diagram, from this item to the referenced one. */
  rel?: string;
  hint?: string;
  /** Changing it moves money, speaks in public or touches personal data. */
  sensitive?: "money" | "public" | "personal";
  unit?: string;
};

export const KIND_LABEL: Record<StudioKind, string> = {
  workflow: "Workflow",
  skill: "Skill",
  agent: "Agent",
  policy: "Policy",
  template: "Template",
  sensor: "Sensor",
  scheduler: "Scheduler",
  loop: "Loop",
  tool: "Tool",
};

export const KIND_PLURAL: Record<StudioKind, string> = {
  workflow: "Workflows",
  skill: "Skills",
  agent: "Agents",
  policy: "Policies",
  template: "Templates",
  sensor: "Sensors",
  scheduler: "Schedulers",
  loop: "Loops",
  tool: "Tools",
};

export const KIND_SYNONYMS: Record<StudioKind, string[]> = {
  workflow: ["workflow", "workflows", "process", "flow"],
  skill: ["skill", "skills", "procedure", "playbook", "sop"],
  agent: ["agent", "agents", "bot", "worker"],
  policy: ["policy", "policies", "rule", "rules", "limit", "threshold", "guardrail"],
  template: ["template", "templates", "report", "register", "log"],
  sensor: ["sensor", "sensors", "source", "signal", "feed", "webhook", "inbox"],
  scheduler: ["scheduler", "schedulers", "schedule", "schedules", "cron", "job", "timer"],
  loop: ["loop", "loops", "feedback loop", "improvement loop"],
  tool: ["tool", "tools", "integration", "api", "action"],
};

/** The order members appear in, everywhere: inputs on the left, actions on the right. */
export const MEMBER_ORDER: MemberKind[] = ["sensor", "scheduler", "agent", "skill", "policy", "tool", "template", "loop"];

export const COMMON_FIELDS: FieldSpec[] = [
  { key: "name", label: "Name", type: "text", synonyms: ["name", "title", "rename", "call it"] },
  { key: "description", label: "Description", type: "longtext", synonyms: ["description", "describe", "summary", "about", "purpose"] },
  { key: "topics", label: "Topics", type: "list", synonyms: ["topic", "topics", "tag", "tags", "label", "labels", "keywords"] },
  { key: "status", label: "Status", type: "select", options: ["active", "draft", "paused", "retired"], synonyms: ["status", "pause", "resume", "activate", "retire", "disable", "enable"] },
  { key: "dri", label: "DRI", type: "person", synonyms: ["dri", "owner", "responsible", "accountable"] },
];

export const FIELD_SPECS: Record<MemberKind, FieldSpec[]> = {
  skill: [
    { key: "trigger", label: "Trigger", type: "text", synonyms: ["trigger", "when", "starts", "fires"] },
    { key: "steps", label: "Steps", type: "list", synonyms: ["step", "steps", "procedure"], hint: "One step per line as kind: text, for example tool: Send reply [tool:chat.reply]" },
    { key: "agents", label: "Run by agents", type: "refs", ref: "agent", rel: "run by", synonyms: ["run by", "assigned", "assign"] },
    { key: "tools", label: "Tools", type: "refs", ref: "tool", rel: "uses", synonyms: ["tool", "tools", "uses"] },
    { key: "policies", label: "Governing policies", type: "refs", ref: "policy", rel: "governed by", synonyms: ["policy", "policies", "governed"] },
    { key: "templates", label: "Fills templates", type: "refs", ref: "template", rel: "fills", synonyms: ["fills", "template", "report"] },
    { key: "inputs", label: "Reads sensors", type: "refs", ref: "sensor", rel: "reads", synonyms: ["input", "inputs", "reads", "sensor"] },
    { key: "outputs", label: "Outputs", type: "list", synonyms: ["output", "outputs", "produces"] },
    { key: "evalCases", label: "Eval cases", type: "number", synonyms: ["eval", "evals", "test cases"] },
  ],
  agent: [
    { key: "autonomy", label: "Autonomy", type: "select", options: ["trainee", "supervised", "autonomous"], synonyms: ["autonomy", "promote", "demote", "supervised", "autonomous", "trainee"] },
    { key: "capabilities", label: "Capabilities", type: "list", synonyms: ["capability", "capabilities", "permission", "permissions", "access"] },
    { key: "accessLevel", label: "Access level", type: "select", options: ["public", "internal", "confidential", "restricted"], synonyms: ["access level", "clearance"] },
    { key: "model", label: "Model", type: "text", synonyms: ["model", "llm"] },
    { key: "maxConcurrent", label: "Max concurrent tasks", type: "number", synonyms: ["concurrent", "parallel", "capacity"] },
  ],
  policy: [
    { key: "statement", label: "Statement", type: "longtext", synonyms: ["statement", "wording", "text", "rule text"] },
    { key: "ruleKind", label: "Rule kind", type: "text", synonyms: ["rule kind", "type of rule"] },
    { key: "criticality", label: "Criticality", type: "select", options: ["0", "1", "2", "3", "4"], synonyms: ["criticality", "risk level"] },
    { key: "validFrom", label: "Valid from", type: "text", synonyms: ["valid from", "effective", "starts on"] },
  ],
  template: [
    { key: "cadence", label: "Cadence", type: "text", synonyms: ["cadence", "frequency", "how often"] },
    { key: "fieldList", label: "Fields", type: "list", synonyms: ["field", "fields", "column", "columns"] },
    { key: "freshnessRule", label: "Freshness rule", type: "text", synonyms: ["freshness", "fresh", "stale"] },
    { key: "requiredEvidence", label: "Required evidence", type: "list", synonyms: ["evidence", "proof"] },
    { key: "sensors", label: "Fed by sensors", type: "refs", ref: "sensor", rel: "fed by", synonyms: ["fed by", "sensor"] },
  ],
  sensor: [
    { key: "source", label: "Source", type: "text", synonyms: ["source", "system", "connector"] },
    { key: "sensorKind", label: "Sensor kind", type: "select", options: ["website", "clarity", "analytics", "inbox", "chat", "payments", "calendar", "crm", "documents", "monitor", "repository"], synonyms: ["sensor kind", "channel"] },
    { key: "events", label: "Events", type: "list", synonyms: ["event", "events", "listens"] },
    { key: "feeds", label: "Feeds agents", type: "refs", ref: "agent", rel: "feeds", synonyms: ["feeds", "subscribers", "subscriber"] },
    { key: "retentionDays", label: "Retention", type: "number", unit: "days", synonyms: ["retention", "keep for", "retain"], sensitive: "personal" },
    { key: "personalData", label: "Carries personal data", type: "boolean", synonyms: ["personal data", "pii"], sensitive: "personal" },
    { key: "health", label: "Health", type: "select", options: ["ok", "degraded", "down"], synonyms: ["health", "down", "degraded"] },
  ],
  scheduler: [
    { key: "cron", label: "Cron", type: "text", synonyms: ["cron", "time", "every", "daily", "weekly", "monthly", "hourly", "at"], hint: "minute hour day month weekday, for example 0 9 * * 1 for Mondays at 09:00" },
    { key: "timezone", label: "Timezone", type: "text", synonyms: ["timezone", "tz"] },
    { key: "target", label: "Runs skill", type: "ref", ref: "skill", rel: "triggers", synonyms: ["runs", "target", "triggers", "skill"] },
    { key: "agent", label: "On agent", type: "ref", ref: "agent", rel: "wakes", synonyms: ["agent", "on agent"] },
    { key: "enabled", label: "Enabled", type: "boolean", synonyms: ["enabled", "on", "off"] },
    { key: "catchUp", label: "Run missed slots", type: "boolean", synonyms: ["catch up", "missed"] },
  ],
  loop: [
    { key: "signal", label: "Signal sensors", type: "refs", ref: "sensor", rel: "senses", synonyms: ["signal", "sensors"] },
    { key: "guards", label: "Guard policies", type: "refs", ref: "policy", rel: "guarded by", synonyms: ["guard", "guards", "policies"] },
    { key: "actions", label: "Action tools", type: "refs", ref: "tool", rel: "acts with", synonyms: ["action", "actions", "tools"] },
    { key: "gate", label: "Quality gate", type: "text", synonyms: ["gate", "quality gate", "check"] },
    { key: "learning", label: "Learns into template", type: "ref", ref: "template", rel: "learns into", synonyms: ["learning", "learns", "report"] },
    { key: "reviewCadence", label: "Review cadence", type: "text", synonyms: ["review", "review cadence"] },
  ],
  tool: [
    { key: "endpoint", label: "Endpoint", type: "text", synonyms: ["endpoint", "url", "api"] },
    { key: "capability", label: "Required capability", type: "text", synonyms: ["capability", "permission"] },
    { key: "sensitivity", label: "Sensitivity", type: "select", options: ["public", "internal", "confidential", "restricted"], synonyms: ["sensitivity"] },
    { key: "sideEffect", label: "Side effect", type: "select", options: ["read", "write", "money", "public"], synonyms: ["side effect", "effect"] },
    { key: "rateLimitPerMin", label: "Rate limit", type: "number", unit: "per minute", synonyms: ["rate limit", "rate", "throttle"] },
  ],
};

/** Policy rule parameters live in fields under "param.<name>". Most are money or time limits. */
export const POLICY_PARAM_LABEL: Record<string, string> = {
  days: "Window in days",
  amountMinor: "Amount limit",
  currency: "Currency",
  mask: "Mask by default",
  gate: "Gate",
  pages: "Guarded pages",
  financeDays: "Finance retention in days",
  chatDays: "Chat retention in days",
  items: "Evidence items",
  cadence: "Review cadence",
};

export const PARAM_SYNONYMS: Record<string, string[]> = {
  days: ["window", "days", "period"],
  amountMinor: ["amount", "limit", "threshold", "cap", "ceiling", "max"],
  mask: ["mask", "masking"],
  pages: ["pages", "page"],
  financeDays: ["finance retention", "finance"],
  chatDays: ["chat retention", "chat"],
  items: ["evidence items", "items"],
  cadence: ["cadence", "how often"],
};

export const isParam = (key: string) => key.startsWith("param.");
export const paramName = (key: string) => key.slice("param.".length);

export function specFor(kind: StudioKind, key: string): FieldSpec | undefined {
  return COMMON_FIELDS.find((f) => f.key === key) ?? (kind === "workflow" ? undefined : FIELD_SPECS[kind].find((f) => f.key === key));
}

export function fieldLabel(kind: StudioKind, key: string) {
  if (isParam(key)) return POLICY_PARAM_LABEL[paramName(key)] ?? paramName(key);
  return specFor(kind, key)?.label ?? key.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase());
}

export function formatValue(v: FieldValue | undefined | null, key?: string): string {
  if (v === undefined || v === null) return "";
  if (Array.isArray(v)) return v.join(", ");
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number" && key?.endsWith("Minor")) return (v / 100).toLocaleString("en-US");
  if (typeof v === "number" && /days$/i.test(key ?? "")) return `${v} days`;
  return String(v);
}

/** Every reference an item makes to another item, read from its ref fields. */
export function refsOf(kind: MemberKind, fields: Record<string, FieldValue>): { key: string; ref: MemberKind; rel: string; id: string }[] {
  const out: { key: string; ref: MemberKind; rel: string; id: string }[] = [];
  for (const spec of FIELD_SPECS[kind]) {
    if ((spec.type !== "refs" && spec.type !== "ref") || !spec.ref) continue;
    const v = fields[spec.key];
    const ids = Array.isArray(v) ? v : typeof v === "string" && v ? [v] : [];
    for (const id of ids) out.push({ key: spec.key, ref: spec.ref, rel: spec.rel ?? "uses", id });
  }
  return out;
}

const CRON_RE = /^(\*|[0-9,\-/*]+)\s+(\*|[0-9,\-/*]+)\s+(\*|[0-9,\-/*]+)\s+(\*|[0-9,\-/*]+)\s+(\*|[0-9,\-/*A-Za-z]+)$/;
export function validCron(s: string) {
  return CRON_RE.test(s.trim());
}

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
export function describeCron(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return cron;
  const [m, h, dom, , dow] = parts;
  const time = /^\d+$/.test(h) && /^\d+$/.test(m) ? `${h.padStart(2, "0")}:${m.padStart(2, "0")}` : null;
  if (h === "*" && /^\d+$/.test(m)) return `Every hour at :${m.padStart(2, "0")}`;
  if (dom === "*" && dow === "*" && time) return `Every day at ${time}`;
  if (dom === "*" && /^\d$/.test(dow) && time) return `Every ${DAYS[Number(dow)]} at ${time}`;
  if (dom === "*" && dow === "1-5" && time) return `Weekdays at ${time}`;
  if (/^\d+$/.test(dom) && dow === "*" && time) return `Day ${dom} of each month at ${time}`;
  return cron;
}
