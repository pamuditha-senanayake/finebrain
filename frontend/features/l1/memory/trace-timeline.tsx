"use client";

// trace-timeline.tsx: one trace from start to end as a numbered step line: what came in, where it went, each step
// and why, the rules it was held to, every access check, and how it ended. Steps are text, never buttons.
// Used by: app/(l1)/l1/memory/traces/[id]/page.tsx. Uses: areas.ts, components/brain, lib/api/hooks.
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";
import type { TraceDetail } from "@/contracts";
import { PageHeader, QueryView, SampleBadge } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { useMemoryMap, useTrace } from "@/lib/api/hooks";
import { dateTime, duration } from "@/lib/format";
import { cn } from "@/lib/utils";
import { AREA_COLOR } from "./areas";
import { ConfirmSurprise } from "./memory-actions";
import { NotConnected, notConnected } from "./memory";

export function TraceTimeline() {
  const { id } = useParams<{ id: string }>();
  const trace = useTrace(id);
  const map = useMemoryMap();
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2"><Link href="/l1/memory/traces"><ArrowLeft /> Traces</Link></Button>
      {notConnected(trace.error) ? <NotConnected /> : <QueryView query={trace} rows={8}>
        {(t) => (
          <>
            <PageHeader title={t.subject} eyebrow={map.data?.isSample ? <SampleBadge /> : undefined} description={`${t.source === "outside" ? "Done outside Finebrain" : "Done by Finebrain"} · ${dateTime(t.startedAt)}`} />
            <ol className="space-y-0" aria-label="Trace, start to end">{stages(t, map.data?.areas.find((a) => a.key === t.area)?.name ?? t.area)}</ol>
            <Links trace={t} sample={!!map.data?.isSample} />
          </>
        )}
      </QueryView>}
    </div>
  );
}

// The six stages every trace has, in order. Work holds the steps themselves, each with its why.
function stages(t: TraceDetail, areaName: string) {
  const list: [string, ReactNode][] = [
    ["What came in", <p key="in" className="text-[15px]">{t.source === "outside" ? "A refund made by hand in Stripe" : "A request through a connected channel"} <span className="text-muted-foreground">· {t.inputRef}</span></p>],
    ["Where it went", <AreaLine key="area" trace={t} areaName={areaName} />],
    ["The work", <WorkSteps key="work" trace={t} />],
    ["Rules it was held to", <Rules key="rules" trace={t} />],
    ["Access checks", <Access key="access" trace={t} />],
    ["How it ended", <p key="end" className="text-[15px]">{t.outcome} <span className="text-muted-foreground">· {policyWords(t)}</span></p>],
  ];
  return list.map(([title, body], i) => <Stage key={title} n={i + 1} title={title} last={i === list.length - 1}>{body}</Stage>);
}

function Stage({ n, title, last, children }: { n: number; title: string; last: boolean; children: ReactNode }) {
  return (
    <li className="relative flex gap-5 pb-8">
      {!last && <span className="absolute left-[15px] top-9 bottom-0 w-px bg-border" aria-hidden />}
      <span className="flex size-8 shrink-0 items-center justify-center rounded-full border bg-card text-[13px] font-semibold tabular-nums" aria-hidden>{n}</span>
      <div className="min-w-0 flex-1 space-y-2 pt-1">
        <h2 className="text-[15px] font-semibold">{title}</h2>
        {children}
      </div>
    </li>
  );
}

function AreaLine({ trace, areaName }: { trace: TraceDetail; areaName: string }) {
  const surprise = trace.match === "surprise";
  return (
    <p className="flex flex-wrap items-center gap-2 text-[15px]">
      <span className="size-2.5 rounded-full" style={{ background: AREA_COLOR[trace.area] }} aria-hidden />
      {areaName}
      <span className={cn("rounded-full px-2 text-[13px]", surprise ? "bg-primary/12 font-medium text-primary" : "text-muted-foreground")}>
        {surprise ? "Surprise: not a known pattern" : "Normal: a known pattern"}
      </span>
    </p>
  );
}

function WorkSteps({ trace }: { trace: TraceDetail }) {
  return (
    <ul className="space-y-3">
      {trace.steps.map((s) => (
        <li key={s.id} className="rounded-xl border px-4 py-3">
          <p className="text-[15px]">{s.title} <span className="text-muted-foreground">· {s.decision}</span></p>
          {s.reason && <p className="mt-1 text-[13px] text-muted-foreground">Why: {s.reason}</p>}
          <p className="mt-1 text-[12px] text-muted-foreground">{duration(s.durationMs)}{s.tool ? ` · ${s.tool}` : ""}</p>
        </li>
      ))}
    </ul>
  );
}

function Rules({ trace }: { trace: TraceDetail }) {
  if (!trace.policies.length && !trace.skill) return <p className="text-[15px] text-muted-foreground">No rule applied.</p>;
  return (
    <ul className="space-y-1.5 text-[15px]">
      {trace.policies.map((p) => (
        <li key={p.id}>{p.name} <span className="text-muted-foreground">· v{p.version}, valid from {p.validFrom.slice(0, 10)}{p.validTo ? ` to ${p.validTo.slice(0, 10)}` : ""}</span></li>
      ))}
      {trace.skill && <li>Skill {trace.skill.id} <span className="text-muted-foreground">· v{trace.skill.version}</span></li>}
    </ul>
  );
}

function Access({ trace }: { trace: TraceDetail }) {
  if (!trace.access.length) return <p className="text-[15px] text-muted-foreground">No checked actions.</p>;
  return (
    <ul className="space-y-2">
      {trace.access.map((a, i) => (
        <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-[15px]">
          <span className={cn("font-medium", a.decision === "deny" && "text-risk")}>{a.decision === "allow" ? "Allowed" : "Denied"}</span>
          <span>{a.action}</span>
          <span className="text-[13px] text-muted-foreground">{a.principal}{a.onBehalfOf ? ` for ${a.onBehalfOf}` : ""} · {a.latencyMs} ms · {a.reason}</span>
        </li>
      ))}
    </ul>
  );
}

function policyWords(t: TraceDetail) {
  if (t.policyCheck === "outside") return "outside the policy in force";
  if (t.policyCheck === "within") return "within policy";
  return "policy not checked";
}

function Links({ trace, sample }: { trace: TraceDetail; sample: boolean }) {
  if (!trace.runId && trace.match !== "surprise") return null;
  return (
    <div className="space-y-5 border-t pt-6">
      {trace.match === "surprise" && <ConfirmSurprise traceId={trace.id} sample={sample} />}
      {trace.runId && <Button asChild variant="outline"><Link href={`/l3/runs/${trace.runId}`}>Open the run</Link></Button>}
    </div>
  );
}
