// intake.ts: the guided intake for demo tenants, in the browser. It follows the backend's rules (backend/app/api/
// intake_policy.py is the source of truth) closely enough to walk the flow: guess, ask what is missing, refuse to file early.
// Used by: handlers.ts.
import { http, HttpResponse, delay } from "msw";
import { db, OpError } from "./db";

type Fields = Record<string, unknown>;
type Draft = { intakeId: string; filename: string; fields: Fields; text: string; status: "asking" | "filed"; documentId: string | null };

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
  return { intakeId: draft.intakeId, filename: draft.filename, fields: draft.fields, questions: asks, ready: asks.length === 0, status: draft.status, documentId: draft.documentId, preview: draft.text.slice(0, 400) };
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
  http.post("*/api/t/:tenant/intake/:id/file", async ({ params }) => {
    try {
      const draft = drafts.get(String(params.id));
      if (!draft) throw new OpError("not_found", 404);
      const asks = questions(draft.fields);
      if (asks.length) throw new OpError(`missing:${asks.map((q) => q.field).join(",")}`, 409);
      const d = db.tenant(String(params.tenant));
      const f = draft.fields;
      const title = [f.kind === "meeting" ? "Meeting" : KINDS[f.kind as keyof typeof KINDS], f.about_name ?? "Company", f.date, f.topic ?? f.title].join(" · ");
      const doc = { id: draft.documentId ?? `doc-in-${Date.now().toString(36)}`, tenantId: d.tenant.id, clusterId: d.clusters[0]?.id ?? "", title, source: "Lisena upload", type: String(f.kind), sensitivity: "internal" as const, extractionStatus: "done" as const, linkedFacts: [], retentionDays: 365, filingRule: "uploads", uploadedBy: "", uploadedAt: new Date(db.now()).toISOString(), sizeKb: 1, personalData: false, meta: f, on: true };
      if (draft.status !== "filed") d.documents.unshift(doc);
      Object.assign(draft, { status: "filed", documentId: doc.id });
      return HttpResponse.json(doc, { status: 202 });
    } catch (e) {
      return fail(e);
    }
  }),
];
