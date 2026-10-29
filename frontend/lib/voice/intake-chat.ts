"use client";

// intake-chat.ts: adding a document by talking to Lisena. "I need to upload a document" asks for the file; once it is
// attached, every typed or spoken reply goes to the intake (backend intake_talk.py reads it) until it is filed or
// stopped. Each reply comes back as an answer with a card: choose a file, pick an option, check and confirm, or done.
// Used by: agent.ts. Uses: lib/api/client.ts, backend intake.py.
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import * as C from "@/contracts";
import type { AskAnswer, IntakeDraft } from "@/contracts";
import { apiPost, apiUpload } from "@/lib/api/client";

// Config
const WANTS_UPLOAD = /\b(upload|add|file|import|put in|attach|save)\b.*\b(document|doc|file|transcript|meeting|minutes|record|contract|report|proposal|receipt|invoice)s?\b/i;
const STOP = /^(cancel|stop|never ?mind|forget it)\b/i;
const LABEL: Record<string, string> = { kind: "Kind", title: "Name", date: "Date", about: "About", about_name: "Client or project", owner: "Owner",
  meeting_type: "Meeting", attendees: "Attended", topic: "Topic", parties: "Parties", vendor: "Paid to", amount: "Amount", currency: "Currency", category: "For", repeats: "Repeats" };

export type IntakeCard =
  | { kind: "attach" }
  | { kind: "question" }
  | { kind: "choices"; options: string[] }
  | { kind: "review"; rows: [string, string][] }
  | { kind: "filed"; documentId: string; tasks: number; spend: boolean };
export type ChatAnswer = AskAnswer & { intake?: IntakeCard };

/** The intake this chat is filling, if any. Kept for this tab, so a reload mid-way still sends the next reply to it. */
type Open = { intakeId: string | null; waitingFile: boolean };
const useIntakeChat = create<Open>()(
  persist((): Open => ({ intakeId: null, waitingFile: false }), { name: "cb.intake.v1", storage: createJSONStorage(() => sessionStorage) }),
);
const patch = (p: Partial<Open>) => useIntakeChat.setState(p);

/** True when this message belongs to the intake: asking to add a document, or a reply while one is open. */
export function takesOver(q: string) {
  const { intakeId, waitingFile } = useIntakeChat.getState();
  return !!intakeId || waitingFile || WANTS_UPLOAD.test(q);
}

export const isWaitingForFile = () => useIntakeChat.getState().waitingFile;

/** One reply in the intake. Before a file: ask for it. With one open: send the words and show what comes back. */
export async function intakeReply(q: string): Promise<ChatAnswer> {
  const { intakeId, waitingFile } = useIntakeChat.getState();
  if (!intakeId) {
    if (waitingFile && STOP.test(q.trim())) return patch({ waitingFile: false }), answer(q, "Okay. Nothing was added.");
    patch({ waitingFile: true });
    return answer(q, "Sure. Choose the file and I will ask a few questions before I add it.", { kind: "attach" });
  }
  const draft = await apiPost(`intake/${intakeId}/say`, { text: q }, C.IntakeDraft);
  return fromDraft(q, draft);
}

/** The file is attached: Lisena reads it and asks the first thing she needs. */
export async function intakeStart(file: File): Promise<ChatAnswer> {
  const form = new FormData();
  form.append("file", file);
  const draft = await apiUpload("intake", form, C.IntakeDraft);
  patch({ waitingFile: false, intakeId: draft.intakeId });
  return fromDraft(`Attached ${file.name}`, draft);
}

export function forgetIntake() {
  patch({ intakeId: null, waitingFile: false });
}

function fromDraft(q: string, draft: IntakeDraft): ChatAnswer {
  if (draft.status !== "asking") patch({ intakeId: null });
  const words = draft.reply ?? "";
  if (draft.status === "filed" && draft.documentId) return answer(q, words, { kind: "filed", documentId: draft.documentId, tasks: draft.tasks?.length ?? 0, spend: !!draft.spend });
  if (draft.status !== "asking") return answer(q, words);
  const next = draft.questions[0];
  if (next?.options) return answer(q, words, { kind: "choices", options: Object.values(next.options) });
  if (draft.ready) return answer(q, words, { kind: "review", rows: rows(draft.fields) });
  return answer(q, words, { kind: "question" }); // a typed or spoken answer; the card only keeps the whole question in view
}

// A choice shows its words, not its id ("Client meeting", not "client"); backend intake_policy.py holds the same lists
const CHOICES: Record<string, Record<string, string>> = {
  kind: { meeting: "Meeting record", contract: "Contract", proposal: "Proposal", policy: "Company policy", report: "Report", spec: "Spec or plan", receipt: "Receipt or invoice", other: "Other document" },
  about: { company: "The company", client: "A client", project: "A project" },
  meeting_type: { client: "Client meeting", internal: "Internal meeting", project: "Project meeting" },
  category: { software: "Software and tools", cloud: "Cloud and hosting", people: "People and contractors", office: "Office", travel: "Travel", marketing: "Marketing", fees: "Bank and legal fees", other: "Other" },
  repeats: { once: "Just once", monthly: "Every month", yearly: "Every year" },
};

function rows(fields: Record<string, unknown>): [string, string][] {
  const shown = (key: string, value: unknown) => (Array.isArray(value) ? value.join(", ") : key === "amount" ? Number(value).toLocaleString(undefined, { minimumFractionDigits: 2 }) : CHOICES[key]?.[String(value)] ?? String(value));
  return Object.keys(LABEL).filter((key) => fields[key] !== undefined).map((key) => [LABEL[key], shown(key, fields[key])]);
}

const answer = (question: string, text: string, intake?: IntakeCard): ChatAnswer => ({ question, answer: text, citations: [], withheld: 0, intake });
