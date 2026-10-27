"use client";

// One paper. First the headline: the preregistered hypothesis, its locked threshold, what was observed with its interval,
// and the verdict. Then the conditions side by side, the cases one at a time, and the run's details folded away.
// An invalid run hides the headline and says which gate failed. With no Lab run yet, the sample view.
import { ArrowLeft, FlaskConical } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Bar, BarChart, CartesianGrid, ErrorBar, XAxis, YAxis } from "recharts";
import type { LabResults, ResearchPaper } from "@/contracts/research";
import { CardPager, Folded } from "@/components/brain/card-pager";
import { KeyValue, Mono, PageHeader, QueryView, Section } from "@/components/brain/primitives";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ChartContainer } from "@/components/ui/chart";
import { CaseViewer } from "./cases";
import { latestFor } from "./home";
import { useExperiments, useResults } from "./lab-api";
import { PAPERS, VerdictChip, percent, points } from "./lab-ui";
import { SampleMetrics } from "./sample-metrics";

const GATE_WORDS: Record<string, string> = {
  canaries: "A canary question was answered wrong, so the pipeline has a defect.",
  retrieval: "Retrieval did not reach the evidence often enough (below 60%).",
  baseline: "The baseline answered almost nothing, so comparing with it says nothing.",
};

export function ResearchPaperPage() {
  const paperKey = (useParams<{ paper: string }>().paper ?? "policies") as ResearchPaper;
  const chosen = useSearchParams().get("experiment");
  const paper = PAPERS.find((p) => p.key === paperKey) ?? PAPERS[0];
  const experiments = useExperiments();
  const latest = chosen ?? latestFor(experiments.data, paper.key)?.id ?? null;
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow={<Link href="/research" className="inline-flex items-center gap-1 hover:text-foreground"><ArrowLeft className="size-3" /> All papers</Link>}
        title={paper.label}
        description={paper.question}
        actions={<Button asChild variant="outline"><Link href="/research/lab/new"><FlaskConical /> New experiment</Link></Button>}
      />
      {latest ? <LabResultsView id={latest} /> : <SampleMetrics paper={paper.key} />}
    </div>
  );
}

function LabResultsView({ id }: { id: string }) {
  const results = useResults(id);
  return (
    <QueryView query={results}>
      {(data) => (
        <div className="space-y-6">
          {data.experiment.status === "invalid_run" ? <InvalidRun data={data} /> : <Headlines data={data} />}
          <ConditionChart data={data} />
          <Section title="Cases" description={data.experiment.paper === "security" ? "One episode at a time." : "One graded answer at a time."}>
            <CaseViewer experimentId={id} conditions={data.experiment.conditions} labels={data.conditions} failedLabel={data.experiment.paper === "security" ? "Failed only" : undefined} />
          </Section>
          <Folded title="Run details"><RunDetails data={data} /></Folded>
        </div>
      )}
    </QueryView>
  );
}

function InvalidRun({ data }: { data: LabResults }) {
  const checks = ((data.experiment.notes.gates as { checks?: Record<string, boolean> } | undefined)?.checks) ?? {};
  const failed = Object.entries(checks).filter(([, ok]) => !ok).map(([gate]) => gate);
  return (
    <Alert variant="destructive">
      <AlertTitle className="text-[15px]">Invalid run: no verdict can be read</AlertTitle>
      <AlertDescription className="text-[15px]">
        <ul className="mt-1 list-disc pl-5">{failed.map((gate) => <li key={gate}>{GATE_WORDS[gate] ?? gate}</li>)}</ul>
      </AlertDescription>
    </Alert>
  );
}

function Headlines({ data }: { data: LabResults }) {
  if (data.verdicts.length === 0) return <Section title="No verdict yet">This run has no results stored.</Section>;
  return (
    <CardPager items={data.verdicts} getId={(v) => v.hypothesisId} label="Hypotheses" render={(verdict) => {
      const hypothesis = data.hypotheses.find((h) => h.id === verdict.hypothesisId);
      const [first, second] = hypothesis?.conditions ?? [];
      const name = (code?: string) => (code ? data.conditions[code] ?? code : "");
      return (
        <section className="rounded-2xl border bg-card p-6 shadow-xs" aria-label={`Hypothesis ${verdict.hypothesisId}`}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[13px] font-medium text-muted-foreground">{verdict.hypothesisId} · {verdict.metricKey.replaceAll("_", " ")}</div>
              <div className="mt-1 text-[17px] font-semibold">{second ? `${name(first)} vs ${name(second)}` : name(first)}</div>
            </div>
            <VerdictChip verdict={verdict.verdict} />
          </div>
          <div className="mt-5 text-4xl font-semibold tracking-tight tabular">{observed(verdict.observed, !!second).value}</div>
          <p className="mt-2 text-[15px] tabular">{observed(verdict.observed, !!second).detail}</p>
          <p className="mt-1 text-[15px] text-muted-foreground">Locked threshold: {hypothesis ? `${hypothesis.comparator.replace("_", " ")} ${shown(hypothesis.threshold, !!second)}` : verdict.threshold}. Test: {verdict.test.replaceAll("_", " ")}.</p>
          {verdict.diagnosisStage && verdict.verdict !== "supported" && <p className="mt-1 text-[15px]">Diagnosis stage {verdict.diagnosisStage}.</p>}
        </section>
      );
    }} />
  );
}

const shown = (value: number, isEffect: boolean) => (isEffect ? points(value) : percent(value));

/** "+0.123 [+0.05, +0.20], p 0.01" read as points for an effect or as a share for one condition, with its interval and p. */
function observed(text: string, isEffect: boolean): { value: string; detail: string } {
  const [value, low, high] = (text.match(/[+-]?\d+\.\d+/g) ?? []).map(Number);
  const p = text.match(/p ([\d.e-]+)/)?.[1];
  if (!Number.isFinite(value)) return { value: text, detail: "" };
  const pText = p === undefined ? "" : Number(p) < 0.0001 ? " · p < 0.0001" : ` · p ${Number(p).toFixed(4)}`;
  return { value: shown(value, isEffect), detail: Number.isFinite(low) ? `95% interval ${shown(low, isEffect)} to ${shown(high, isEffect)}${pText}` : "" };
}

function ConditionChart({ data }: { data: LabResults }) {
  const metric = data.hypotheses[0]?.metric ?? "stale_answer_rate";
  const rows = data.metrics.filter((m) => m.key === metric).map((m) => ({
    name: data.conditions[m.condition] ?? m.condition, value: m.value * 100,
    err: [(m.value - (m.ci?.low ?? m.value)) * 100, ((m.ci?.high ?? m.value) - m.value) * 100],
  }));
  if (rows.length === 0) return null;
  const top = Math.min(100, Math.max(20, Math.ceil(Math.max(...rows.map((r) => r.value + r.err[1])) / 10) * 10 + 10));  // from zero, scaled to the data
  return (
    <Section title={rows.length ? data.metrics.find((m) => m.key === metric)?.label : ""} description="Each condition with its 95% interval.">
      <ChartContainer config={{ value: { label: "Share", color: "var(--chart-1)" } }} className="h-56 w-full">
        <BarChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={13} />
          <YAxis unit="%" domain={[0, top]} width={44} fontSize={12} />
          <Bar dataKey="value" fill="var(--color-value)" radius={6} isAnimationActive={false}>
            <ErrorBar dataKey="err" width={6} strokeWidth={1.5} stroke="var(--foreground)" />
          </Bar>
        </BarChart>
      </ChartContainer>
      <ul className="mt-3 space-y-1 text-[15px]">
        {data.metrics.filter((m) => m.key === metric).map((m) => (
          <li key={m.condition} className="flex justify-between"><span>{data.conditions[m.condition] ?? m.condition}</span><span className="tabular">{percent(m.value)} of {m.n}</span></li>
        ))}
      </ul>
    </Section>
  );
}

/** The access check's time at the call, per condition that checks (security only). */
function latency(data: LabResults): [string, string][] {
  const of = (key: string, c: string) => data.metrics.find((m) => m.key === key && m.condition === c && (m.n ?? 0) > 0)?.value;
  return data.experiment.conditions.filter((c) => of("check_latency_p50_ms", c) !== undefined)
    .map((c) => [`Access check, ${data.conditions[c] ?? c}`, `${of("check_latency_p50_ms", c)} ms median, ${of("check_latency_p95_ms", c)} ms p95`]);
}

function RunDetails({ data }: { data: LabResults }) {
  const e = data.experiment;
  return (
    <KeyValue className="text-[15px]" items={[
      ["Status", e.status.replaceAll("_", " ")],
      ["Model", e.models.answer],
      ["Seeds and trials", `${e.seeds.length} seeds, ${e.trials} trial${e.trials > 1 ? "s" : ""}`],
      ["Cost", `$${(e.costUsd ?? 0).toFixed(4)} of $${e.budgetUsd}`],
      ["Code", <Mono key="g">{e.gitCommit}</Mono>],
      ["Config hash", <Mono key="c">{e.configSha256.slice(0, 16)}</Mono>],
      ["Preregistration hash", <Mono key="p">{data.preregSha256?.slice(0, 16) ?? "none"}</Mono>],
      ...latency(data),
      ["Ingest", <pre key="i" className="whitespace-pre-wrap text-[12px]">{JSON.stringify(e.notes.ingest ?? {}, null, 1)}</pre>],
    ]} />
  );
}
