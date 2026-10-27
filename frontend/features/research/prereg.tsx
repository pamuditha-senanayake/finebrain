"use client";

// Preregistrations: the thresholds each paper is judged by, written down before any run. A draft can change; locking
// needs the title typed back, stamps a hash, and from then on nothing can change it.
import { ArrowLeft, Lock, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { LabHypothesis, LabPrereg, ResearchPaper } from "@/contracts/research";
import { CardPager } from "@/components/brain/card-pager";
import { EmptyState, KeyValue, Mono, PageHeader, QueryView, StatusChip } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { problemsOf, useCreatePrereg, useLockPrereg, usePreregs } from "./lab-api";
import { LabGate, PAPERS, paperLabel } from "./lab-ui";

const METRICS = ["stale_answer_rate", "as_of_now_current", "control_accuracy", "canary_accuracy", "refusal_rate", "mixed_rate", "retrieval_either_recall"];
const COMPARATORS: LabHypothesis["comparator"][] = ["at_most", "below", "at_least", "above"];
const TESTS: LabHypothesis["test"][] = ["exact_mcnemar", "paired_bootstrap", "wilson", "rule_of_three", "bootstrap_mean"];
const CONDITIONS = ["C0", "C1", "C3"];
const blank = (n: number): LabHypothesis => ({ id: `H${n}`, metric: "stale_answer_rate", comparator: "at_most", threshold: -0.1, conditions: ["C3", "C0"], test: "exact_mcnemar", alpha: 0.05 });

export function Preregistrations() {
  const preregs = usePreregs();
  const [drafting, setDrafting] = useState(false);
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader eyebrow={<Link href="/research" className="inline-flex items-center gap-1 hover:text-foreground"><ArrowLeft className="size-3" /> Research</Link>}
        title="Preregistrations" description="Thresholds written down and locked before the first run. A locked one never changes."
        actions={<Button onClick={() => setDrafting(true)}><Plus /> New draft</Button>} />
      <LabGate>
        <QueryView query={preregs} empty={<EmptyState title="No preregistrations yet" description="Write the hypotheses a paper will be judged by, then lock them." action={<Button size="sm" variant="outline" onClick={() => setDrafting(true)}><Plus /> New draft</Button>} />}>
          {(rows) => <CardPager items={rows} getId={(p) => p.id} label="Preregistrations" render={(p) => <PreregCard prereg={p} />} />}
        </QueryView>
        <DraftDialog open={drafting} onOpenChange={setDrafting} />
      </LabGate>
    </div>
  );
}

function PreregCard({ prereg }: { prereg: LabPrereg }) {
  const [locking, setLocking] = useState(false);
  return (
    <section className="rounded-2xl border bg-card p-6 shadow-xs">
      <div className="flex items-start justify-between gap-3">
        <div><div className="text-[13px] text-muted-foreground">{paperLabel(prereg.paper)}</div><h2 className="text-[17px] font-semibold">{prereg.title}</h2></div>
        {prereg.lockedAt ? <StatusChip tone="ok"><Lock className="size-3" /> Locked</StatusChip> : <StatusChip tone="warn">Draft</StatusChip>}
      </div>
      <ul className="mt-4 space-y-2 text-[15px]">
        {prereg.hypotheses.map((h) => (
          <li key={h.id}><span className="font-medium">{h.id}</span> · {h.metric.replaceAll("_", " ")}, {h.conditions.join(" minus ")} {h.comparator.replace("_", " ")} {h.threshold} ({h.test.replaceAll("_", " ")}, α {h.alpha})</li>
        ))}
      </ul>
      <KeyValue className="mt-4 text-[15px]" items={[["Hash", <Mono key="h">{prereg.sha256.slice(0, 16)}</Mono>], ...(prereg.lockedAt ? [["Locked", `${prereg.lockedBy} · ${prereg.lockedAt.slice(0, 16).replace("T", " ")}`] as [string, string]] : [])]} />
      {!prereg.lockedAt && <div className="mt-5 flex justify-end"><Button onClick={() => setLocking(true)}><Lock /> Lock</Button></div>}
      <LockDialog prereg={prereg} open={locking} onOpenChange={setLocking} />
    </section>
  );
}

function LockDialog({ prereg, open, onOpenChange }: { prereg: LabPrereg; open: boolean; onOpenChange: (open: boolean) => void }) {
  const lock = useLockPrereg();
  const [typed, setTyped] = useState("");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Lock “{prereg.title}”?</DialogTitle>
          <DialogDescription>After this the thresholds can never change, by anyone. Type the title to confirm.</DialogDescription>
        </DialogHeader>
        <Label htmlFor="confirm-title" className="text-[15px]">Title</Label>
        <Input id="confirm-title" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        {lock.error && <p role="alert" className="text-[15px] text-risk">{(lock.error as Error).message}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={typed.trim() !== prereg.title || lock.isPending} onClick={() => lock.mutate({ id: prereg.id, confirm: typed }, { onSuccess: () => onOpenChange(false) })}>Lock for good</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function DraftDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const create = useCreatePrereg();
  const [paper, setPaper] = useState<ResearchPaper>("policies");
  const [title, setTitle] = useState("");
  const [rows, setRows] = useState<LabHypothesis[]>([blank(1)]);
  const change = (i: number, patch: Partial<LabHypothesis>) => setRows(rows.map((row, j) => (j === i ? { ...row, ...patch } : row)));
  const save = () => create.mutate({ paper, title, hypotheses: rows }, { onSuccess: () => { onOpenChange(false); setTitle(""); setRows([blank(1)]); } });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>New draft</DialogTitle>
          <DialogDescription>One condition: the threshold is its share. Two: the first minus the second, as a share (−0.10 is ten points lower).</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2"><Label className="text-[15px]">Paper</Label>
            <Select value={paper} onValueChange={(v) => setPaper(v as ResearchPaper)}><SelectTrigger className="w-full" aria-label="Paper"><SelectValue /></SelectTrigger>
              <SelectContent>{PAPERS.map((p) => <SelectItem key={p.key} value={p.key}>{p.label}</SelectItem>)}</SelectContent></Select></div>
          <div className="space-y-2"><Label htmlFor="draft-title" className="text-[15px]">Title</Label><Input id="draft-title" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
        </div>
        <ul className="space-y-3">
          {rows.map((row, i) => (
            <li key={i} className="grid grid-cols-2 gap-2 rounded-xl border p-3 sm:grid-cols-3">
              <Pick label="Metric" value={row.metric} choices={METRICS} onChange={(metric) => change(i, { metric })} />
              <Pick label="First condition" value={row.conditions[0]} choices={CONDITIONS} onChange={(c) => change(i, { conditions: [c, ...row.conditions.slice(1)] })} />
              <Pick label="Compared with" value={row.conditions[1] ?? "none"} choices={["none", ...CONDITIONS]} onChange={(c) => change(i, { conditions: c === "none" ? [row.conditions[0]] : [row.conditions[0], c] })} />
              <Pick label="Must be" value={row.comparator} choices={COMPARATORS} onChange={(c) => change(i, { comparator: c as LabHypothesis["comparator"] })} />
              <div className="space-y-1"><Label className="text-[13px]">Threshold</Label><Input type="number" step={0.01} aria-label="Threshold" value={row.threshold} onChange={(e) => change(i, { threshold: Number(e.target.value) })} /></div>
              <Pick label="Test" value={row.test} choices={TESTS} onChange={(t) => change(i, { test: t as LabHypothesis["test"] })} />
              {rows.length > 1 && <Button variant="ghost" size="sm" className="justify-self-start" onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 /> Remove</Button>}
            </li>
          ))}
        </ul>
        <Button variant="outline" size="sm" className="justify-self-start" onClick={() => setRows([...rows, blank(rows.length + 1)])}><Plus /> Add hypothesis</Button>
        {create.error && <ul role="alert" className="list-disc space-y-1 pl-5 text-[15px] text-risk">{problemsOf(create.error).map((p) => <li key={p}>{p}</li>)}</ul>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!title.trim() || create.isPending} onClick={save}>Save draft</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Pick({ label, value, choices, onChange }: { label: string; value: string; choices: string[]; onChange: (v: string) => void }) {
  return (
    <div className="space-y-1"><Label className="text-[13px]">{label}</Label>
      <Select value={value} onValueChange={onChange}><SelectTrigger className="w-full" aria-label={label}><SelectValue /></SelectTrigger>
        <SelectContent>{choices.map((c) => <SelectItem key={c} value={c}>{c.replaceAll("_", " ")}</SelectItem>)}</SelectContent></Select>
    </div>
  );
}
