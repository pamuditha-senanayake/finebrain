"use client";

// New experiment in three steps: pack and thresholds, conditions and repeats, budget and model. Creating shows the cost
// estimate first; nothing is spent until "Start run". Every problem the server finds is listed before anything runs.
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { LabExperiment, LabOptions, LabPack, LabPrereg } from "@/contracts/research";
import { PageHeader, QueryView, Section } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { problemsOf, useCreateExperiment, useOptions, usePacks, usePreregs, useStartExperiment } from "./lab-api";
import { LabGate, StepLine, paperLabel } from "./lab-ui";

const STEPS = ["Pack and thresholds", "Conditions and repeats", "Budget and model"];
const PAPER_OF_KIND: Record<string, "policies" | "security"> = { freshness: "policies", security: "security" };

type Draft = { packId: string; preregId: string; conditions: string[]; seeds: number; trials: number; model: string; budget: string };

export function NewExperiment() {
  const packs = usePacks();
  const preregs = usePreregs();
  const options = useOptions();
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader eyebrow={<Link href="/research/lab" className="inline-flex items-center gap-1 hover:text-foreground"><ArrowLeft className="size-3" /> Lab</Link>} title="New experiment" />
      <LabGate>
        <QueryView query={{ ...options, data: packs.data && preregs.data && options.data ? { packs: packs.data, preregs: preregs.data, options: options.data } : undefined, isLoading: packs.isLoading || preregs.isLoading || options.isLoading }}>
          {(loaded) => <Steps {...loaded} />}
        </QueryView>
      </LabGate>
    </div>
  );
}

function Steps({ packs, preregs, options }: { packs: LabPack[]; preregs: LabPrereg[]; options: LabOptions }) {
  const router = useRouter();
  const create = useCreateExperiment();
  const start = useStartExperiment();
  const [step, setStep] = useState(0);
  const [d, setD] = useState<Draft>({ packId: "", preregId: "", conditions: [], seeds: 3, trials: 1, model: options.models[0]?.id ?? "", budget: "5" });
  const pack = packs.find((p) => p.id === d.packId);
  const paper = pack ? PAPER_OF_KIND[pack.kind] : undefined;
  const locked = preregs.filter((p) => p.lockedAt && p.paper === paper);
  const prereg = locked.find((p) => p.id === d.preregId);
  const created: LabExperiment | undefined = create.data;
  const conditions = (paper && options.conditionsByPaper?.[paper]) || options.conditions;

  const choosePrereg = (id: string) => {
    const needed = [...new Set(preregs.find((p) => p.id === id)?.hypotheses.flatMap((h) => h.conditions) ?? [])].sort();
    setD({ ...d, preregId: id, conditions: needed });
  };
  const submit = () => paper && create.mutate({ paper, packId: d.packId, preregId: d.preregId, conditions: d.conditions,
    seeds: Array.from({ length: d.seeds }, (_, i) => i + 1), trials: d.trials, model: d.model, budgetUsd: Number(d.budget) });
  const run = (id: string) => start.mutate(id, { onSuccess: () => router.push(`/research/lab/${id}`) });

  return (
    <div>
      <StepLine steps={STEPS} current={created ? 3 : step} />
      {step === 0 && (
        <Section title="Which pack, judged by which thresholds?">
          <Field label="Pack">
            <Select value={d.packId} onValueChange={(packId) => setD({ ...d, packId, preregId: "", conditions: [] })}>
              <SelectTrigger className="w-full" aria-label="Pack"><SelectValue placeholder="Choose a pack" /></SelectTrigger>
              <SelectContent>{packs.map((p) => <SelectItem key={p.id} value={p.id} disabled={!PAPER_OF_KIND[p.kind]}>{p.name} v{p.version}{PAPER_OF_KIND[p.kind] ? "" : ` (${p.kind} runs later)`}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Locked preregistration" hint={pack && !locked.length ? <>None locked for {paperLabel(paper ?? "")} yet. <Link className="underline" href="/research/prereg">Lock one first.</Link></> : undefined}>
            <Select value={d.preregId} onValueChange={choosePrereg} disabled={!locked.length}>
              <SelectTrigger className="w-full" aria-label="Locked preregistration"><SelectValue placeholder="Choose the thresholds" /></SelectTrigger>
              <SelectContent>{locked.map((p) => <SelectItem key={p.id} value={p.id}>{p.title}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
        </Section>
      )}
      {step === 1 && (
        <Section title="Which conditions, how many times?" description={prereg ? `Your preregistration compares ${[...new Set(prereg.hypotheses.flatMap((h) => h.conditions))].join(" and ")}.` : undefined}>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Conditions">
            {conditions.map((c) => {
              const on = d.conditions.includes(c.code);
              return (
                <button key={c.code} type="button" disabled={!c.available} aria-pressed={on} title={c.reason}
                  onClick={() => setD({ ...d, conditions: on ? d.conditions.filter((x) => x !== c.code) : [...d.conditions, c.code].sort() })}
                  className={cn("rounded-full border px-3 py-1.5 text-[15px]", on ? "border-foreground bg-foreground text-background" : "hover:border-foreground/40", !c.available && "cursor-not-allowed opacity-50")}>
                  {c.code} · {c.label}
                </button>
              );
            })}
          </div>
          {conditions.filter((c) => !c.available).map((c) => <p key={c.code} className="mt-2 text-[13px] text-muted-foreground">{c.code} is not offered: {c.reason}.</p>)}
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <Field label="Seeds"><NumberSelect value={d.seeds} choices={[1, 3, 5]} onChange={(seeds) => setD({ ...d, seeds })} label="Seeds" /></Field>
            <Field label="Trials per question"><NumberSelect value={d.trials} choices={[1, 2, 4, 8]} onChange={(trials) => setD({ ...d, trials })} label="Trials" /></Field>
          </div>
        </Section>
      )}
      {step === 2 && !created && (
        <Section title="Which model, and the most it may spend?">
          <Field label="Answering model">
            <Select value={d.model} onValueChange={(model) => setD({ ...d, model })}>
              <SelectTrigger className="w-full" aria-label="Answering model"><SelectValue /></SelectTrigger>
              <SelectContent>{options.models.map((m) => <SelectItem key={m.id} value={m.id}>{m.id} · ${m.inUsdPerMillion} in, ${m.outUsdPerMillion} out per million tokens</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label={`Cost cap in dollars (at most ${options.maxBudgetUsd})`}>
            <Input type="number" min={0.01} max={options.maxBudgetUsd} step={0.5} value={d.budget} onChange={(e) => setD({ ...d, budget: e.target.value })} />
          </Field>
          {create.error && <ul role="alert" className="mt-3 list-disc space-y-1 pl-5 text-[15px] text-risk">{problemsOf(create.error).map((p) => <li key={p}>{p}</li>)}</ul>}
        </Section>
      )}
      {created && <Estimate experiment={created} onStart={() => run(created.id)} starting={start.isPending} error={start.error} />}
      {!created && (
        <div className="mt-6 flex justify-between">
          <Button variant="outline" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</Button>
          {step < 2
            ? <Button disabled={step === 0 ? !d.packId || !d.preregId : d.conditions.length === 0} onClick={() => setStep(step + 1)}>Next: {STEPS[step + 1].toLowerCase()}</Button>
            : <Button disabled={create.isPending || !Number(d.budget)} onClick={submit}>{create.isPending ? "Estimating…" : "Next: see the cost"}</Button>}
        </div>
      )}
    </div>
  );
}

function Estimate({ experiment, onStart, starting, error }: { experiment: LabExperiment; onStart: () => void; starting: boolean; error: unknown }) {
  const estimate = experiment.notes.estimate as { cases: number; usd: number } | undefined;
  return (
    <Section title="Ready to run" description="Nothing has been spent yet.">
      <p className="text-[15px]">{estimate?.cases ?? 0} answers, about <span className="font-semibold">${(estimate?.usd ?? 0).toFixed(2)}</span>. The run stops at ${experiment.budgetUsd} whatever happens.</p>
      {error ? <p role="alert" className="mt-2 text-[15px] text-risk">{(error as Error).message}</p> : null}
      <div className="mt-5 flex justify-end"><Button disabled={starting} onClick={onStart}>{starting ? "Starting…" : "Start run"}</Button></div>
    </Section>
  );
}

function Field({ label, hint, children }: { label: string; hint?: React.ReactNode; children: React.ReactNode }) {
  return <div className="mt-4 space-y-2 first:mt-0"><Label className="text-[15px]">{label}</Label>{children}{hint && <p className="text-[13px] text-muted-foreground">{hint}</p>}</div>;
}

function NumberSelect({ value, choices, onChange, label }: { value: number; choices: number[]; onChange: (n: number) => void; label: string }) {
  return (
    <Select value={String(value)} onValueChange={(v) => onChange(Number(v))}>
      <SelectTrigger className="w-full" aria-label={label}><SelectValue /></SelectTrigger>
      <SelectContent>{choices.map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}</SelectContent>
    </Select>
  );
}
