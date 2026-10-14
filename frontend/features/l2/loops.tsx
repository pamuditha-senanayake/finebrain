"use client";

import { useReducedMotion } from "motion/react";
import { lazy, Suspense, useState } from "react";
import { Eye, FlaskConical, Play, Square, ThumbsDown, ThumbsUp } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import type { Experiment } from "@/contracts";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Beam } from "@/components/brain/motion";
import { WorkflowFilter, countByMany } from "@/components/brain/category-filter";
import { PersonChip, useLookup } from "@/components/brain/names";
import { useWorkflowIndex } from "@/lib/workflow-index";
import { CritBadge, LoadingState, Mono, PageHeader, QueryView, Section, Status } from "@/components/brain/primitives";
import { useChangeRequests, useExperiments, useLoop, useLoops, useOp } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { pct } from "@/lib/format";

// React.lazy, not next/dynamic: the chunk loads only when this view renders, never on route prefetch.
const LoopCanvas = lazy(() => import("./loop-canvas"));

export function LoopsIndex() {
  const loops = useLoops();
  const lookup = useLookup();
  const index = useWorkflowIndex();
  const [wf, setWf] = useState("all");
  return (
    <div>
      <PageHeader title="Loops" description="Every function is a loop: sensor, policy, tool, quality gate, learning, and back to the sensor. A loop that runs with little intervention keeps improving." />
      <QueryView query={loops}>
        {(all) => {
          const ls = wf === "all" ? all : all.filter((l) => index.of("loop", l.id).includes(wf));
          return (
          <div className="space-y-3">
          <WorkflowFilter value={wf} onChange={setWf} options={countByMany(all, (l) => index.of("loop", l.id))} />
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {ls.map((l) => (
              <li key={l.id}>
                <Link href={`/l2/loops/${l.id}`} className="block rounded-xl border bg-card p-4 hover:border-primary/40">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold">{l.name}</h3>
                      <p className="text-xs text-muted-foreground">{lookup.cluster(l.clusterId)}{index.of("loop", l.id).length > 0 && ` · ${index.of("loop", l.id).join(", ")}`}</p>
                    </div>
                    {l.stages.some((s) => s.pending > 0) && <Status value="pending" />}
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{l.description}</p>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                    <div><div className="font-semibold tabular">{l.runs7d.toLocaleString()}</div><div className="text-muted-foreground">runs 7d</div></div>
                    <div><div className="font-semibold tabular">{pct(l.successRate)}</div><div className="text-muted-foreground">success</div></div>
                    <div><div className="font-semibold tabular">{pct(l.autonomyRate)}</div><div className="text-muted-foreground">autonomy</div></div>
                  </div>
                  <ol className="mt-3 flex items-center gap-1 text-[10px] text-muted-foreground" aria-label="Stages">
                    {l.stages.map((s, i) => (
                      <li key={s.key} className="flex items-center gap-1">
                        <span className="rounded bg-muted px-1 py-0.5 capitalize">{s.key}</span>
                        {i < l.stages.length - 1 && <span aria-hidden>→</span>}
                      </li>
                    ))}
                  </ol>
                </Link>
              </li>
            ))}
          </ul>
          </div>
          );
        }}
      </QueryView>
    </div>
  );
}

function ExperimentCard({ exp }: { exp: Experiment }) {
  const { user } = useCurrentUser();
  const lookup = useLookup();
  const crs = useChangeRequests();
  const cr = crs.data?.find((c) => c.id === exp.changeRequestId);
  const preview = useOp<{ experimentId: string }>("experimentPreview", { success: "Sandbox branch created with an impact preview" });
  const start = useOp<{ experimentId: string }>("experimentStart", { success: "A/B experiment started" });
  const conclude = useOp<{ experimentId: string }>("experimentConclude", { success: "Experiment concluded" });
  const keep = useOp<{ experimentId: string }>("experimentKeep", { success: "Kept. The pricing page change goes to L1." });
  const discard = useOp<{ experimentId: string }>("experimentDiscard", { success: "Discarded and recorded as learning" });
  const canAct = !!user && user.tier !== "L3";
  return (
    <Beam active={exp.status === "running"} className="rounded-xl">
      <div className="rounded-xl border bg-card p-4" data-testid={`experiment-${exp.id}`}>
        <div className="flex flex-wrap items-center gap-2">
          <FlaskConical className="size-4 text-primary" />
          <h3 className="text-sm font-semibold">{exp.title}</h3>
          <CritBadge level={exp.criticality} />
          <span className="ml-auto flex gap-1.5">
            <Status value={exp.status} />
            {exp.impact && <Status value={exp.impact} />}
          </span>
        </div>
        <p className="mt-2 text-sm">{exp.hypothesis}</p>
        <p className="mt-1 text-xs text-muted-foreground">Signal: {exp.signal} Proposed by {lookup.name(exp.proposedBy)}.</p>
        <table className="mt-3 w-full text-xs">
          <thead className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
            <tr><th className="py-1 font-medium">Variant</th><th className="py-1 font-medium">Traffic</th><th className="py-1 text-right font-medium">Conversion</th></tr>
          </thead>
          <tbody>
            {exp.variants.map((v) => (
              <tr key={v.id} className="border-t">
                <td className="py-1.5">{v.id} · {v.name}</td>
                <td className="py-1.5">{pct(v.traffic)}</td>
                <td className="py-1.5 text-right tabular">{v.conversion == null ? "·" : pct(v.conversion, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {exp.branch && <p className="mt-2 text-xs">Branch <Mono>{exp.branch}</Mono></p>}
        {exp.learning && <p className="mt-2 rounded-md bg-surface p-2 text-xs"><span className="font-medium">Learning:</span> {exp.learning}</p>}
        {cr && (
          <p className="mt-2 text-xs">
            Change request <Link href={`/l2/versioning/${cr.id}`} className="text-primary hover:underline">{cr.title}</Link> · <Status value={cr.status} />
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {exp.status === "proposed" && <Button size="sm" onClick={() => preview.mutate({ experimentId: exp.id })} disabled={!canAct || preview.isPending}><Eye /> Preview on a sandbox branch</Button>}
          {exp.status === "previewed" && <Button size="sm" onClick={() => start.mutate({ experimentId: exp.id })} disabled={!canAct || start.isPending}><Play /> Start A/B experiment</Button>}
          {exp.status === "running" && <Button size="sm" onClick={() => conclude.mutate({ experimentId: exp.id })} disabled={!canAct || conclude.isPending}><Square /> Conclude</Button>}
          {exp.status === "concluded" && (
            <>
              <Button size="sm" onClick={() => keep.mutate({ experimentId: exp.id })} disabled={!canAct || keep.isPending}><ThumbsUp /> Keep and ship</Button>
              <Button size="sm" variant="outline" onClick={() => discard.mutate({ experimentId: exp.id })} disabled={!canAct || discard.isPending}><ThumbsDown /> Discard</Button>
            </>
          )}
          {["previewed", "running"].includes(exp.status) && <Button size="sm" variant="ghost" onClick={() => discard.mutate({ experimentId: exp.id })} disabled={!canAct}>Discard</Button>}
        </div>
      </div>
    </Beam>
  );
}

export function LoopDetail() {
  const reduceMotion = useReducedMotion();
  const { id } = useParams<{ id: string }>();
  const loop = useLoop(id);
  const experiments = useExperiments();
  return (
    <QueryView query={loop}>
      {(l) => (
        <div>
          <PageHeader eyebrow={<Link href="/l2/loops" className="hover:underline">Loops</Link>} title={l.name} description={l.description} actions={<span className="text-xs">DRI <PersonChip id={l.dri} /></span>} />
          <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
            <Section title="Loop canvas" description="Live metrics per stage. Pending items wait at the quality gate.">
              <Suspense fallback={<LoadingState rows={4} label="Loading loop canvas" />}><LoopCanvas loop={l} /></Suspense>
            </Section>
            <Section title="Run history, 14 days">
              <ChartContainer config={{ runs: { label: "Runs", color: "var(--chart-1)" } }} className="h-[300px] w-full">
                <BarChart data={l.history.map((h) => ({ ...h, day: h.day.slice(5) }))}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="day" tickLine={false} axisLine={false} fontSize={11} />
                  <YAxis tickLine={false} axisLine={false} fontSize={11} width={30} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar isAnimationActive={!reduceMotion} dataKey="runs" fill="var(--color-runs)" radius={3} />
                </BarChart>
              </ChartContainer>
            </Section>
          </div>
          {l.experiments.length > 0 && (
            <div className="mt-4">
              <h2 className="mb-2 text-sm font-semibold">Experiments</h2>
              <QueryView query={experiments}>
                {(es) => (
                  <div className="grid gap-3 lg:grid-cols-2">
                    {es.filter((e) => e.loopId === l.id).map((e) => <ExperimentCard key={e.id} exp={e} />)}
                  </div>
                )}
              </QueryView>
            </div>
          )}
        </div>
      )}
    </QueryView>
  );
}
