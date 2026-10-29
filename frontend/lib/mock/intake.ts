// intake.ts: the guided intake for demo tenants, in the browser. It follows the backend's rules (backend/app/api/
// intake_policy.py is the source of truth) closely enough to walk the flow: guess, ask what is missing, refuse to file early.
// Used by: handlers.ts.
import { http, HttpResponse, delay } from "msw";
import { db, OpError } from "./db";

type Fields = Record<string, unknown>;
type Draft = { intakeId: string; filename: string; fields: Fields; text: string; status: "asking" | "filed" | "stopped"; documentId: string | null; reply?: string; tasks?: unknown[] };

const KINDS = { meeting: "Meeting record", contract: "Contract", proposal: "Proposal", policy: "Company policy", report: "Report", spec: "Spec or plan", other: "Other document" };
const ABOUT = { company: "The company", client: "A client", project: "A project" };
const MEETING_TYPES = { client: "Client meeting", internal: "Internal meeting", project: "Project meeting" };
const FIELDS: [string, string, "text" | "date" | "list" | "choice", string, Record<string, string>?][] = [
  ["kind", "What kind of document is this?", "choice", "*", KINDS],
  ["title", "What should we call it?", "text", "*"],
  ["date", "What date is it from?", "date", "*"],
  ["about", "Is it about the company, a client or a project?", "choice", "*", ABOUT],
  ["about_name", "Which client or project?", "text", "client_or_project"],
  ["owner", "Who owns it on our side?", "text", "*"],
  ["meeting_type", "What kind of meeting was it?", "choice", "meeting", MEETING_TYPES],
  ["attendees", "Who attended? Separate names with commas.", "list", "meeting"],
  ["topic", "What was the meeting about, in a few words?", "text", "meeting"],
  ["parties", "Who are the parties to it? Separate names with commas.", "list", "contract"],
];
const drafts = new Map<string, Draft>();

function questions(fields: Fields) {
  const needed = FIELDS.filter(([, , , rule]) => rule === "*" || rule === fields.kind || (rule === "client_or_project" && (fields.about === "client" || fields.about === "project")));
  return needed.filter(([name]) => fields[name] === undefined).map(([field, question, type, , options]) => ({ field, question, type, options: options ?? null }));
}

function clean(name: string, value: unknown): unknown {
  const spec = FIELDS.find(([field]) => field === name);
  if (!spec || value === undefined || value === null) return undefined;
  const [, , type, , options] = spec;
  if (type === "list") {
    const names = (Array.isArray(value) ? value : String(value).split(",")).map((v) => String(v).trim()).filter(Boolean);
    return names.length ? names : undefined;
  }
  const text = String(value).trim();
  if (type === "choice") return options && text in options ? text : undefined;
  if (type === "date") return /^\d{4}-\d{2}-\d{2}$/.test(text.slice(0, 10)) ? text.slice(0, 10) : undefined;
  return text || undefined;
}

function view(draft: Draft) {
  const asks = questions(draft.fields);
  return { intakeId: draft.intakeId, filename: draft.filename, fields: draft.fields, questions: asks, ready: asks.length === 0, status: draft.status, documentId: draft.documentId, preview: draft.text.slice(0, 400), reply: draft.reply ?? "", tasks: draft.tasks ?? [] };
}

// --- The chat (backend intake_talk.py says it in full)

const LABELS: Record<string, string[]> = { title: ["name", "title"], date: ["date"], owner: ["owner"], about_name: ["client", "project"], topic: ["topic"], attendees: ["attendees", "people"], meeting_type: ["meeting type", "meeting"], about: ["about"], kind: ["kind"], parties: ["parties"] };
const askOf = (q: { question: string; options: Record<string, string> | null }) => q.question + (q.options ? ` (${Object.values(q.options).join(", ")})` : "");
const SHOWN: Record<string, string> = { kind: "Kind", title: "Name", date: "Date", about: "About", about_name: "Client or project", owner: "Owner", meeting_type: "Meeting", attendees: "Attended", topic: "Topic", parties: "Parties" };
const labelOf = (k: string, v: unknown) => (Array.isArray(v) ? v.join(", ") : FIELDS.find(([f]) => f === k)?.[4]?.[String(v)] ?? String(v));
const summary = (f: Fields) => Object.keys(SHOWN).filter((k) => f[k] !== undefined).map((k) => `${SHOWN[k]}: ${labelOf(k, f[k])}`).join("; ");

function cleanSaid(name: string, said: string): unknown {
  const spec = FIELDS.find(([field]) => field === name);
  if (spec?.[2] === "choice" && spec[4]) {
    const lower = said.toLowerCase();
    return Object.entries(spec[4]).find(([id, label]) => lower === id || lower === label.toLowerCase() || lower.includes(id))?.[0];
  }
  return clean(name, said.replace(/^(it'?s|it is|it was|the)\s+/i, ""));
}

function talk(draft: Draft, said: string) {
  const text = said.trim().replace(/[.!]$/, "");
  const asking = questions(draft.fields)[0]?.field;
  if (/^(cancel|stop)/i.test(text)) return Object.assign(draft, { status: "stopped", reply: "Okay, I stopped. Nothing was added." });
  const change = text.match(/^(?:change|set|update)\s+(?:the\s+)?([a-z ]+?)\s+to\s+(.+)$/i);
  const field = change && Object.entries(LABELS).find(([, words]) => words.includes(change[1].toLowerCase()))?.[0];
  let prefix = "";
  if (field && change) {
    const v = cleanSaid(field, change[2]);
    if (v !== undefined) {
      draft.fields[field] = v;
      prefix = "Changed. ";
    }
  } else if (asking && !/^(yes|sure|ok)/i.test(text)) {
    const v = cleanSaid(asking, text);
    if (v === undefined) return Object.assign(draft, { reply: `Sorry, that does not answer it. ${askOf(questions(draft.fields)[0])}` });
    draft.fields[asking] = v;
    prefix = "Got it. ";
  } else if (/^(yes|sure|ok)/i.test(text) && !asking) return null; // file it
  const next = questions(draft.fields)[0];
  return Object.assign(draft, { reply: next ? prefix + askOf(next) : `${prefix}Here is what I have. ${summary(draft.fields)}. Shall I add it to the knowledge base?` });
}

function guess(filename: string, text: string): Fields {
  const speakers = [...new Set([...text.matchAll(/^\s*([A-Z][\w .'-]{1,40}):\s/gm)].map((m) => m[1].trim()))];
  const meeting = speakers.length >= 2 || /transcript|meeting|minutes|call/i.test(filename);
  const date = (text.match(/\b(20\d\d-\d\d-\d\d)\b/) ?? filename.match(/\b(20\d\d-\d\d-\d\d)\b/))?.[1];
  const fields: Fields = { title: filename.replace(/\.[^.]+$/, "").replace(/_/g, " ") };
  if (meeting) Object.assign(fields, { kind: "meeting", ...(speakers.length ? { attendees: speakers } : {}) });
  if (date) fields.date = date;
  return fields;
}

const fail = (e: unknown) => (e instanceof OpError ? HttpResponse.json({ error: e.message }, { status: e.status }) : HttpResponse.json({ error: "Internal error" }, { status: 500 }));

export const intakeHandlers = [
  http.get("*/api/t/:tenant/intake/policy", () =>
    HttpResponse.json({ policy: ["Nothing joins the knowledge base until every required field is filled.", "A meeting also says its type, who attended and its topic.", "Meeting records are what was said, never company rules."], steps: [], kinds: KINDS }),
  ),
  http.post("*/api/t/:tenant/intake", async ({ request }) => {
    await delay(300);
    const file = (await request.formData()).get("file") as File | null;
    if (!file) return HttpResponse.json({ error: "No file" }, { status: 400 });
    const text = await file.text();
    const draft: Draft = { intakeId: `intake-${Date.now().toString(36)}`, filename: file.name, fields: guess(file.name, text), text, status: "asking", documentId: null };
    const first = questions(draft.fields)[0];
    draft.reply = `I read it. ${draft.fields.kind === "meeting" ? "It looks like a meeting record. " : ""}${first ? askOf(first) : "Shall I add it?"}`;
    drafts.set(draft.intakeId, draft);
    return HttpResponse.json(view(draft), { status: 201 });
  }),
  http.post("*/api/t/:tenant/intake/:id/answer", async ({ params, request }) => {
    const draft = drafts.get(String(params.id));
    if (!draft) return HttpResponse.json({ error: "not_found" }, { status: 404 });
    const given = ((await request.json()) as { fields?: Fields }).fields ?? {};
    for (const [name, value] of Object.entries(given)) {
      const kept = clean(name, value);
      if (kept !== undefined) draft.fields[name] = kept;
    }
    return HttpResponse.json(view(draft));
  }),
  http.post("*/api/t/:tenant/intake/:id/say", async ({ params, request }) => {
    const draft = drafts.get(String(params.id));
    if (!draft) return HttpResponse.json({ error: "not_found" }, { status: 404 });
    if (draft.status !== "asking") return HttpResponse.json(view(Object.assign(draft, { reply: "That one is already finished." })));
    const text = ((await request.json()) as { text?: string }).text ?? "";
    if (talk(draft, text)) return HttpResponse.json(view(draft));
    const doc = fileIt(String(params.tenant), draft);
    const made = tasksFrom(draft, doc.id, doc.title);
    draft.tasks = made;
    draft.reply = `Done. I added it as ${doc.title}.` + (made.length ? ` I also made ${made.length} ${made.length === 1 ? "task" : "tasks"} from its action points.` : "");
    return HttpResponse.json(view(draft));
  }),
  http.post("*/api/t/:tenant/intake/:id/file", async ({ params }) => {
    try {
      const draft = drafts.get(String(params.id));
      if (!draft) throw new OpError("not_found", 404);
      const asks = questions(draft.fields);
      if (asks.length) throw new OpError(`missing:${asks.map((q) => q.field).join(",")}`, 409);
      return HttpResponse.json(fileIt(String(params.tenant), draft), { status: 202 });
    } catch (e) {
      return fail(e);
    }
  }),
];

function fileIt(tenant: string, draft: Draft) {
  const d = db.tenant(tenant);
  const f = draft.fields;
  const title = [f.kind === "meeting" ? "Meeting" : KINDS[f.kind as keyof typeof KINDS], f.about_name ?? "Company", f.date, f.topic ?? f.title].join(" · ");
  const doc = { id: draft.documentId ?? `doc-in-${Date.now().toString(36)}`, tenantId: d.tenant.id, clusterId: d.clusters[0]?.id ?? "", title, source: "Lisena upload", type: String(f.kind), sensitivity: "internal" as const, extractionStatus: "done" as const, linkedFacts: [], retentionDays: 365, filingRule: "uploads", uploadedBy: "", uploadedAt: new Date(db.now()).toISOString(), sizeKb: 1, personalData: false, meta: f, on: true };
  if (draft.status !== "filed") d.documents.unshift(doc);
  Object.assign(draft, { status: "filed", documentId: doc.id });
  return doc;
}

// --- Tasks (backend tasks.py): one per Action line, kept in the browser for demo tenants

type MockTask = { id: string; title: string; owner: string; due: string; status: "open" | "done"; source: { documentId: string; title: string; line: string } | null; createdAt: string; doneAt: string | null };
const tasks = new Map<string, MockTask>();
const ACTION = /\b(action item|to ?do|will send|will share|will follow up|by (monday|tuesday|wednesday|thursday|friday|next week|tomorrow)|owner:)\b/i;
const plusDays = (iso: string, days: number) => new Date(Date.parse(iso) + days * 86_400_000).toISOString().slice(0, 10);

function taskView(t: MockTask) {
  const left = Math.floor((Date.parse(t.due) - db.now()) / 86_400_000);
  return { ...t, state: t.status === "done" ? "done" : left < 0 ? "late" : left <= 1 ? "soon" : "open" };
}

function tasksFrom(draft: Draft, documentId: string, title: string) {
  if (draft.fields.kind !== "meeting") return [];
  return draft.text.split("\n").flatMap((line, i) => {
    if (!ACTION.test(line)) return [];
    const [, who, said] = line.match(/^\s*([A-Z][\w .'-]{1,40}):\s*(.+)$/) ?? [null, null, line];
    const name = String(said).replace(/^(i|we)\s*(will|'ll)\s+/i, "").replace(/\s+by\s+\w+\.?$/i, "").replace(/\.$/, "");
    const t: MockTask = { id: `task-${documentId}-${i}`, title: name.charAt(0).toUpperCase() + name.slice(1), owner: who ?? String(draft.fields.owner), due: plusDays(String(draft.fields.date), 7), status: "open", source: { documentId, title, line: line.trim() }, createdAt: new Date(db.now()).toISOString(), doneAt: null };
    tasks.set(t.id, t);
    return [taskView(t)];
  });
}

export const taskHandlers = [
  http.get("*/api/t/:tenant/tasks", () => HttpResponse.json([...tasks.values()].map(taskView))),
  http.post("*/api/t/:tenant/tasks", async ({ request }) => {
    const body = (await request.json()) as { title?: string; owner?: string; due?: string };
    if (!body.title?.trim() || !body.owner?.trim()) return HttpResponse.json({ error: "empty_title" }, { status: 400 });
    const t: MockTask = { id: `task-${Date.now().toString(36)}`, title: body.title.trim(), owner: body.owner.trim(), due: body.due ?? plusDays(new Date(db.now()).toISOString(), 7), status: "open", source: null, createdAt: new Date(db.now()).toISOString(), doneAt: null };
    tasks.set(t.id, t);
    return HttpResponse.json(taskView(t), { status: 201 });
  }),
  http.post("*/api/t/:tenant/tasks/:id", async ({ params, request }) => {
    const t = tasks.get(String(params.id));
    if (!t) return HttpResponse.json({ error: "not_found" }, { status: 404 });
    const body = (await request.json()) as Partial<MockTask>;
    Object.assign(t, body, body.status ? { doneAt: body.status === "done" ? new Date(db.now()).toISOString() : null } : {});
    return HttpResponse.json(taskView(t));
  }),
];
