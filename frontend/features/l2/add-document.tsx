"use client";

// add-document.tsx: adding any document to the knowledge base as a short guided talk. Choose the file; Lisena fills what
// the text says and asks, one question at a time, for what is still missing; check it all on one card; file it. Opens from
// the Library, Lisena's paperclip, or saying "upload a meeting transcript". Used by: components/shell/app-shell.tsx.
// Uses: lib/api/upload.ts (intake hooks), backend intake.py and intake_policy.py (the rules).
import { Check, FileUp, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { create } from "zustand";
import type { IntakeDraft, IntakeQuestion } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { UPLOAD_TYPES, useAnswerIntake, useFileIntake, useIntakeRules, useStartIntake } from "@/lib/api/upload";
import { cn } from "@/lib/utils";

// Config
const STEPS = ["File", "Details", "Check", "Filed"];
const LABEL: Record<string, string> = {
  kind: "Kind", title: "Name", date: "Date", about: "About", about_name: "Client or project", owner: "Owner",
  meeting_type: "Meeting", attendees: "Attended", topic: "Topic", parties: "Parties", vendor: "Paid to", amount: "Amount", currency: "Currency", category: "For", repeats: "Repeats",
};
// Spoken requests that open this dialog: "upload a meeting transcript", "add a document", "file these minutes"
const WANTS_UPLOAD = /\b(upload|add|file|import|put in)\b.*\b(document|doc|file|transcript|meeting|minutes|record|contract|report|proposal)s?\b/i;

/** Open from anywhere: the Library button, Lisena's paperclip, or a spoken request. */
export const useAddDocument = create<{ open: boolean; setOpen: (open: boolean) => void }>()((set) => ({ open: false, setOpen: (open) => set({ open }) }));
export const openAddDocument = () => useAddDocument.getState().setOpen(true);
export const wantsUpload = (words: string) => WANTS_UPLOAD.test(words);

export function AddDocumentDialog() {
  const { open, setOpen } = useAddDocument();
  const start = useStartIntake();
  const answer = useAnswerIntake();
  const file = useFileIntake();
  const [draft, setDraft] = useState<IntakeDraft | null>(null);
  const [editing, setEditing] = useState<string | null>(null); // a field reopened from the check card
  const [error, setError] = useState("");
  const filed = file.data;
  const question: IntakeQuestion | undefined = editing ? questionFor(editing, draft) : draft?.questions[0];
  const step = filed ? 3 : !draft ? 0 : question ? 1 : 2;

  function reset() {
    setDraft(null);
    setEditing(null);
    setError("");
    start.reset();
    file.reset();
  }

  // Step 1: the file goes up and comes back with what it already says
  async function choose(chosen: File | undefined) {
    if (!chosen) return;
    setError("");
    try {
      setDraft(await start.mutateAsync(chosen));
    } catch (e) {
      const reason = e instanceof Error ? e.message : "";
      setError(reason.startsWith("unsupported_type") ? "That file type cannot be read. Use text, Markdown, CSV, PDF or Word." : reason === "too_large" ? "That file is over 10 MB." : "The file could not be read. Try again.");
    }
  }

  // Step 2: one answer at a time; a refused answer brings the same question back
  async function give(field: string, value: unknown) {
    if (!draft) return;
    setError("");
    const next = await answer.mutateAsync({ intakeId: draft.intakeId, fields: { [field]: value } });
    if (next.questions[0]?.field === field || (editing && next.fields[field] === undefined)) setError("That does not answer it. Try again.");
    else setEditing(null);
    setDraft(next);
  }

  // Step 3: filed only when the policy is met
  async function send() {
    if (!draft) return;
    setError("");
    try {
      await file.mutateAsync(draft.intakeId);
    } catch {
      setError("It could not be filed. Check the details and try again.");
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); if (!next) reset(); }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add a document</DialogTitle>
          <DialogDescription>A few questions first, so it is filed in the right place.</DialogDescription>
        </DialogHeader>
        <StepLine current={step} />

        {step === 0 && <FilePicker busy={start.isPending} onPick={(f) => void choose(f)} />}
        {step === 1 && draft && question && (
          <Ask key={`${question.field}-${editing ?? ""}`} question={question} draft={draft} busy={answer.isPending} left={editing ? null : draft.questions.length} onAnswer={(v) => void give(question.field, v)} onBack={editing ? () => setEditing(null) : reset} />
        )}
        {step === 2 && draft && <Review draft={draft} busy={file.isPending} onChange={setEditing} onFile={() => void send()} onBack={reset} />}
        {step === 3 && filed && <Done title={filed.title} onAnother={reset} onClose={() => setOpen(false)} />}

        {error && <p role="alert" className="text-[15px] text-risk">{error}</p>}
      </DialogContent>
    </Dialog>
  );
}

function questionFor(field: string, draft: IntakeDraft | null): IntakeQuestion | undefined {
  const open = draft?.questions.find((q) => q.field === field);
  if (open) return open;
  const known: Record<string, IntakeQuestion> = {
    kind: { field: "kind", question: "What kind of document is this?", type: "choice", options: { meeting: "Meeting record", contract: "Contract", proposal: "Proposal", policy: "Company policy", report: "Report", spec: "Spec or plan", receipt: "Receipt or invoice", other: "Other document" } },
    about: { field: "about", question: "Is it about the company, a client or a project?", type: "choice", options: { company: "The company", client: "A client", project: "A project" } },
    meeting_type: { field: "meeting_type", question: "What kind of meeting was it?", type: "choice", options: { client: "Client meeting", internal: "Internal meeting", project: "Project meeting" } },
    title: { field: "title", question: "What should we call it?", type: "text" },
    vendor: { field: "vendor", question: "Who was it paid to?", type: "text" },
    amount: { field: "amount", question: "How much was it, with the currency? For example, 49 dollars.", type: "text" },
    currency: { field: "currency", question: "Which currency?", type: "choice", options: { USD: "US dollars", LKR: "Sri Lankan rupees", EUR: "Euros", GBP: "British pounds" } },
    category: { field: "category", question: "What was it for?", type: "choice", options: { software: "Software and tools", cloud: "Cloud and hosting", people: "People and contractors", office: "Office", travel: "Travel", marketing: "Marketing", fees: "Bank and legal fees", other: "Other" } },
    repeats: { field: "repeats", question: "Does it repeat?", type: "choice", options: { once: "Just once", monthly: "Every month", yearly: "Every year" } },
    date: { field: "date", question: "What date is it from?", type: "date" },
    about_name: { field: "about_name", question: "Which client or project?", type: "text" },
    owner: { field: "owner", question: "Who owns it on our side?", type: "text" },
    topic: { field: "topic", question: "What was the meeting about, in a few words?", type: "text" },
    attendees: { field: "attendees", question: "Who attended? Separate names with commas.", type: "list" },
    parties: { field: "parties", question: "Who are the parties to it? Separate names with commas.", type: "list" },
  };
  return known[field] ?? { field, question: `What is the ${(LABEL[field] ?? field).toLowerCase()}?`, type: "text" };
}

/** Numbered steps: done, current and next. They are a progress line, not buttons. */
function StepLine({ current }: { current: number }) {
  return (
    <ol className="flex items-center gap-2" aria-label="Progress">
      {STEPS.map((name, i) => (
        <li key={name} className="flex flex-1 items-center gap-2" aria-current={i === current ? "step" : undefined}>
          <span className={cn("grid size-6 shrink-0 place-items-center rounded-full text-xs font-medium", i < current ? "bg-primary/15 text-primary" : i === current ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
            {i < current ? <Check className="size-3.5" aria-hidden /> : i + 1}
          </span>
          <span className={cn("text-sm", i === current ? "font-medium" : "text-muted-foreground")}>{name}</span>
          {i < STEPS.length - 1 && <span className="h-px flex-1 bg-border" aria-hidden />}
        </li>
      ))}
    </ol>
  );
}

function FilePicker({ busy, onPick }: { busy: boolean; onPick: (file: File | undefined) => void }) {
  const picker = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div>
      <input ref={picker} type="file" accept={UPLOAD_TYPES} className="hidden" onChange={(e) => { onPick(e.target.files?.[0]); e.target.value = ""; }} aria-label="Document to add" />
      <button
        type="button"
        disabled={busy}
        onClick={() => picker.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); onPick(e.dataTransfer.files[0]); }}
        className={cn("flex w-full flex-col items-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center outline-none transition-colors hover:border-primary/50 focus-visible:ring-4 focus-visible:ring-ring/40", over && "border-primary bg-primary/5")}
      >
        {busy ? <Loader2 className="size-6 animate-spin text-primary" aria-hidden /> : <FileUp className="size-6 text-primary" aria-hidden />}
        <span className="text-[15px] font-medium">{busy ? "Reading it…" : "Choose a file or drop it here"}</span>
        <span className="text-sm text-muted-foreground">Meeting transcripts, contracts, reports and more. Text, Markdown, CSV, PDF or Word, up to 10 MB.</span>
      </button>
    </div>
  );
}

/** Lisena asks one thing. Choices are buttons; everything else is one box, prefilled when the text already said it. */
function Ask({ question, draft, busy, left, onAnswer, onBack }: { question: IntakeQuestion; draft: IntakeDraft; busy: boolean; left: number | null; onAnswer: (value: unknown) => void; onBack: () => void }) {
  const known = draft.fields[question.field];
  const [value, setValue] = useState(Array.isArray(known) ? known.join(", ") : known ? String(known) : "");
  const options = Object.entries(question.options ?? {});
  return (
    <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); if (value.trim()) onAnswer(value.trim()); }}>
      <div className="rounded-2xl rounded-tl-md bg-muted/60 px-4 py-3">
        <p className="text-xs font-medium text-muted-foreground">Lisena · {draft.filename}</p>
        <p className="mt-1 text-[15px]">{question.question}</p>
      </div>
      {options.length > 0 ? (
        <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label={question.question}>
          {options.map(([id, label]) => (
            <button key={id} type="button" role="radio" aria-checked={value === id} disabled={busy} onClick={() => onAnswer(id)} className={cn("rounded-xl border px-4 py-3 text-left text-[15px] outline-none transition-colors hover:border-primary/50 focus-visible:ring-4 focus-visible:ring-ring/40", value === id && "border-primary bg-primary/5")}>
              {label}
            </button>
          ))}
        </div>
      ) : (
        <Input autoFocus type={question.type === "date" ? "date" : "text"} value={value} onChange={(e) => setValue(e.target.value)} aria-label={question.question} placeholder={question.type === "list" ? "Nimal Perera, Sara Silva" : ""} className="h-11 text-[15px]" />
      )}
      <div className="flex items-center justify-between gap-2">
        <Button type="button" variant="ghost" onClick={onBack}>{left === null ? "Back to check" : "Choose another file"}</Button>
        <div className="flex items-center gap-3">
          {left !== null && <span className="text-sm text-muted-foreground">{left === 1 ? "Last question" : `${left} questions left`}</span>}
          {options.length === 0 && <Button type="submit" disabled={busy || !value.trim()}>{busy ? <Loader2 className="animate-spin" /> : "Next"}</Button>}
        </div>
      </div>
    </form>
  );
}

/** Everything on one card before it is filed, each line changeable, with the rules one click away. */
function Review({ draft, busy, onChange, onFile, onBack }: { draft: IntakeDraft; busy: boolean; onChange: (field: string) => void; onFile: () => void; onBack: () => void }) {
  const [rulesOpen, setRulesOpen] = useState(false);
  const rules = useIntakeRules(rulesOpen);
  const shown = Object.keys(LABEL).filter((field) => draft.fields[field] !== undefined);
  return (
    <div className="space-y-5">
      <dl className="divide-y rounded-2xl border">
        {shown.map((field) => (
          <div key={field} className="flex items-center gap-3 px-4 py-2.5">
            <dt className="w-32 shrink-0 text-sm text-muted-foreground">{LABEL[field]}</dt>
            <dd className="min-w-0 flex-1 truncate text-[15px]">{show(field, draft.fields[field])}</dd>
            <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => onChange(field)} aria-label={`Change ${LABEL[field].toLowerCase()}`}>Change</Button>
          </div>
        ))}
      </dl>
      <div>
        <button type="button" className="text-sm text-muted-foreground underline-offset-4 hover:underline" aria-expanded={rulesOpen} onClick={() => setRulesOpen(!rulesOpen)}>How documents are added</button>
        {rulesOpen && rules.data && (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{rules.data.policy.map((line) => <li key={line}>{line}</li>)}</ul>
        )}
      </div>
      <div className="flex items-center justify-between gap-2">
        <Button variant="ghost" onClick={onBack}>Choose another file</Button>
        <Button onClick={onFile} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : "Add to knowledge base"}</Button>
      </div>
    </div>
  );
}

function Done({ title, onAnother, onClose }: { title: string; onAnother: () => void; onClose: () => void }) {
  return (
    <div className="space-y-5 text-center">
      <span className="mx-auto grid size-12 place-items-center rounded-full bg-primary/15 text-primary"><Check className="size-6" aria-hidden /></span>
      <div>
        <p className="text-[15px] font-medium">Filed as {title}</p>
        <p className="mt-1 text-sm text-muted-foreground">It is being read now. Lisena can answer from it in a minute.</p>
      </div>
      <div className="flex justify-center gap-2">
        <Button variant="outline" onClick={onAnother}>Add another</Button>
        <Button asChild onClick={onClose}><Link href="/l2/library">Open Library</Link></Button>
      </div>
    </div>
  );
}

/** A choice shows its label ("Client meeting"), a list its names, anything else as typed. */
function show(field: string, value: unknown): string {
  if (Array.isArray(value)) return value.join(", ");
  return questionFor(field, null)?.options?.[String(value)] ?? String(value);
}
