"use client";

import { useReducedMotion } from "motion/react";
import { Pencil } from "lucide-react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { Skill } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CategoryFilter, WorkflowFilter, countBy, countByMany } from "@/components/brain/category-filter";
import { DataTable, type Column } from "@/components/brain/data-table";
import { AgentChip, useLookup } from "@/components/brain/names";
import { EmptyState, Kpi, KeyValue, Mono, PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useAgents, useNow, useRuns, useSkills, useSkillVersions } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { duration, pct, relTime, usd } from "@/lib/format";
import { studioHref, useWorkflowIndex } from "@/lib/workflow-index";
import { cn } from "@/lib/utils";
import { SkillsFromTraces, useDraftCount } from "./skills-from-traces";

function HealthBars({ s }: { s: Skill }) {
  const rows: [string, number, string][] = [
    ["Task success", s.health.taskSuccess, "finished runs that succeeded without a person"],
    [`Consistency pass^${s.health.k}`, s.health.consistencyPassK, `all ${s.health.k} repeated runs of a case pass`],
    ["Conformance", s.health.conformance, "how closely observed runs follow the documented steps"],
  ];
  return (
    <ul className="space-y-2.5">
      {rows.map(([label, v, hint]) => (
        <li key={label} className="text-xs">
          <div className="mb-1 flex justify-between">
            <span title={hint}>{label}</span>
            <span className={cn("tabular", v < 0.75 ? "text-risk" : v < 0.85 ? "text-warn-fg" : "text-ok")}>{pct(v)}</span>
          </div>
          <Progress value={v * 100} className="h-1.5" aria-label={label} />
        </li>
      ))}
    </ul>
  );
}

export function SkillsStudio() {
  const skills = useSkills();
  const agents = useAgents();
  const router = useRouter();
  const lookup = useLookup();
  const index = useWorkflowIndex();
  const [category, setCategory] = useState("all");
  const [wf, setWf] = useState("all");
  // Related workflows come from each workflow's members (the shared index); a skill's category is its first workflow's lead topic.
  const info = useMemo(() => ({ get: (id: string) => ({ workflows: index.of("skill", id), category: index.category("skill", id) }) }), [index]);
  const categoryOf = (s: Skill) => info.get(s.id)?.category ?? "general";
  const main = useMemo(() => (skills.data ?? []).filter((s) => s.branch === "main" && s.status === "active"), [skills.data]);
  const drafts = useMemo(() => (skills.data ?? []).filter((s) => s.status === "draft"), [skills.data]);
  const fromTraces = useDraftCount();
  const columns: Column<Skill>[] = useMemo(
    () => [
      { id: "name", header: "Skill", width: "minmax(200px,1.6fr)", value: (s) => s.name, cell: (s) => <span className="font-medium">{s.name} <Mono className="text-muted-foreground">v{s.version}</Mono></span> },
      { id: "category", header: "Category", width: "120px", value: (s) => categoryOf(s), cell: (s) => <StatusChip tone="info" className="capitalize">{categoryOf(s)}</StatusChip> },
      { id: "workflow", header: "Related workflows", width: "minmax(180px,1.3fr)", value: (s) => (info.get(s.id)?.workflows ?? []).join(", "), cell: (s) => { const w = info.get(s.id)?.workflows ?? []; return w.length ? <span className="truncate" title={w.join(", ")}>{w.join(", ")}</span> : <span className="text-muted-foreground">none</span>; } },
      { id: "agent", header: "Agent", width: "minmax(140px,1fr)", value: (s) => lookup.name(s.agentIds[0] ?? ""), hideOnMobile: true, cell: (s) => (s.agentIds[0] ? <AgentChip id={s.agentIds[0]} link={false} /> : null) },
      { id: "success", header: "Success", width: "80px", align: "right", value: (s) => s.health.taskSuccess, cell: (s) => pct(s.health.taskSuccess) },
      { id: "passk", header: "pass^k", width: "70px", align: "right", value: (s) => s.health.consistencyPassK, hideOnMobile: true, cell: (s) => pct(s.health.consistencyPassK) },
      { id: "conf", header: "Conformance", width: "100px", align: "right", value: (s) => s.health.conformance, cell: (s) => <span className={cn(s.health.conformance < 0.75 && "text-risk")}>{pct(s.health.conformance)}</span> },
      { id: "evals", header: "Eval cases", width: "84px", align: "right", value: (s) => s.evalSuite.cases, hideOnMobile: true, cell: (s) => s.evalSuite.cases },
      { id: "updated", header: "Updated", width: "100px", value: (s) => s.updatedAt, hideOnMobile: true, cell: (s) => <span className="text-muted-foreground">{relTime(s.updatedAt)}</span> },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lookup, info],
  );
  return (
    <div>
      <PageHeader title="Skills studio and Agent Academy" description="A skill is an employee's documented capability. Eval suites run in a sandbox. Agents move from trainee to supervised to autonomous." />
      <Tabs defaultValue="skills">
        <TabsList>
          <TabsTrigger value="skills">Skills</TabsTrigger>
          <TabsTrigger value="drafts">Drafts {drafts.length > 0 && <span className="ml-1 text-muted-foreground">{drafts.length}</span>}</TabsTrigger>
          <TabsTrigger value="from-traces">From traces {fromTraces > 0 && <span className="ml-1 text-muted-foreground">{fromTraces}</span>}</TabsTrigger>
          <TabsTrigger value="academy">Academy</TabsTrigger>
        </TabsList>
        <TabsContent value="from-traces" className="mt-3">
          <SkillsFromTraces />
        </TabsContent>
        <TabsContent value="skills" className="mt-3">
          <QueryView query={skills}>{() => <DataTable label="Skills" data={main.filter((s) => (category === "all" || categoryOf(s) === category) && (wf === "all" || (info.get(s.id)?.workflows ?? []).includes(wf)))} toolbar={<><CategoryFilter label="Filter by category" allLabel="All categories" value={category} onChange={setCategory} options={countBy(main, categoryOf)} /><WorkflowFilter value={wf} onChange={setWf} options={countByMany(main, (s) => info.get(s.id)?.workflows ?? [])} /></>} columns={columns} getRowId={(s) => `${s.id}@${s.branch}`} focusOf={(s) => `skill:${s.id}`} onRowClick={(s) => router.push(`/l2/skills/${s.id}`)} initialSort={{ id: "conf", desc: false }} height="calc(100dvh - 280px)" />}</QueryView>
        </TabsContent>
        <TabsContent value="drafts" className="mt-3">
          {drafts.length === 0 ? (
            <EmptyState title="No draft skills" description="Skillify a handled conversation, or edit a skill to start one." />
          ) : (
            <ul className="grid gap-2 md:grid-cols-2">
              {drafts.map((s) => (
                <li key={`${s.id}@${s.branch}`} className="rounded-xl border bg-card p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <Link href={`/l2/skills/${s.id}`} className="font-medium hover:underline">{s.name}</Link>
                    <StatusChip tone="info">{s.origin}</StatusChip>
                  </div>
                  <Mono className="mt-1 block text-muted-foreground">{s.branch}</Mono>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>
        <TabsContent value="academy" className="mt-3">
          <QueryView query={agents}>
            {(as) => (
              <div className="grid gap-5 md:grid-cols-3">
                {(["trainee", "supervised", "autonomous"] as const).map((level) => (
                  <Section key={level} title={<span className="capitalize">{level}</span>} description={`${as.filter((a) => a.autonomy === level).length} agents`}>
                    <ul className="max-h-[50vh] space-y-1.5 overflow-auto">
                      {as
                        .filter((a) => a.autonomy === level)
                        .slice(0, 120)
                        .map((a) => (
                          <li key={a.id} className="flex items-center justify-between gap-2 text-sm">
                            <AgentChip id={a.id} />
                            <span className="text-xs tabular text-muted-foreground">{pct(a.taskSuccess)}</span>
                          </li>
                        ))}
                    </ul>
                  </Section>
                ))}
              </div>
            )}
          </QueryView>
        </TabsContent>
      </Tabs>
    </div>
  );
}

const DAY_MS = 86_400_000;

export function SkillEditor() {
  const { id } = useParams<{ id: string }>();
  const versions = useSkillVersions(id);
  return (
    <QueryView query={versions}>
      {(vs) => {
        const live = vs.find((s) => s.branch === "main") ?? vs[0];
        return live ? <SkillDetail live={live} versions={vs} /> : null;
      }}
    </QueryView>
  );
}

/** Read-only skill page: what it is for, how it is used over time, and how healthy it is. Edits happen in Workflow Studio. */
function SkillDetail({ live, versions }: { live: Skill; versions: Skill[] }) {
  const { user } = useCurrentUser();
  const reduce = useReducedMotion();
  const runs = useRuns();
  const now = useNow();
  const index = useWorkflowIndex();
  const links = index.links("skill", live.id);
  const canEdit = !!user && user.tier !== "L3" && live.branch === "main";
  const mine = useMemo(() => (runs.data ?? []).filter((r) => r.skill.id === live.id), [runs.data, live.id]);
  // Requested: every run that called the skill. Completed: runs that finished without escalating or failing.
  const series = useMemo(() => {
    const end = Math.max(now, ...mine.map((r) => Date.parse(r.startedAt)));
    const days = 30;
    const rows = Array.from({ length: days }, (_, i) => {
      const t = end - (days - 1 - i) * DAY_MS;
      return { key: new Date(t).toISOString().slice(0, 10), day: new Date(t).toISOString().slice(5, 10), requested: 0, completed: 0, escalated: 0 };
    });
    const at = new Map(rows.map((r) => [r.key, r]));
    for (const r of mine) {
      const row = at.get(r.startedAt.slice(0, 10));
      if (!row) continue;
      row.requested++;
      if (r.status === "succeeded") row.completed++;
      if (r.status === "escalated" || r.status === "blocked") row.escalated++;
    }
    return rows;
  }, [mine, now]);
  const total = mine.length;
  const done = mine.filter((r) => r.status === "succeeded").length;
  const escalated = mine.filter((r) => r.status === "escalated" || r.status === "blocked").length;
  const avg = (f: (r: (typeof mine)[number]) => number) => (total ? mine.reduce((s, r) => s + f(r), 0) / total : 0);
  const config = { requested: { label: "Wanted (runs requested)", color: "var(--chart-1)" }, completed: { label: "Used (completed)", color: "var(--chart-2)" }, escalated: { label: "Escalated", color: "var(--chart-4)" } } satisfies ChartConfig;
  const byAgent = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of mine) m.set(r.agentId, (m.get(r.agentId) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [mine]);
  return (
    <div>
      <PageHeader
        eyebrow={<Link href="/l2/skills" className="hover:underline">Skills studio</Link>}
        title={`${live.name} v${live.version}`}
        description={<span className="inline-flex flex-wrap items-center gap-1.5"><Status value={live.status} /> on <Mono>{live.branch}</Mono> · {links.length ? links.map((l) => l.wfName).join(", ") : "no workflow yet"}</span>}
        actions={
          canEdit ? (
            <Button asChild>
              <Link href={links[0] ? studioHref(links[0]) : "/studio"}><Pencil /> Edit in Workflow Studio</Link>
            </Button>
          ) : null
        }
      />
      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Section title="What it does" description="Read only. To change the skill, open it in Workflow Studio.">
            <div className="space-y-6">
              <p className="text-sm">{live.trigger}</p>
              <ol className="space-y-1.5 text-sm">
                {live.steps.map((st, i) => (
                  <li key={st.id} className="flex items-start gap-2.5">
                    <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-muted text-[11px] font-semibold tabular">{i + 1}</span>
                    <span>{st.text} <StatusChip tone="neutral" className="ml-1 capitalize">{st.kind.replace("_", " ")}</StatusChip></span>
                  </li>
                ))}
              </ol>
              <KeyValue
                items={[
                  ["Inputs", live.inputs.join(", ") || "none"],
                  ["Outputs", live.outputs.join(", ") || "none"],
                  ["Tools", live.tools.map((t) => t.replace("tool:", "")).join(", ") || "none"],
                  ["Governing policies", live.policies.length ? live.policies.map((p) => <Link key={p} href={`/l2/policies/${p}`} className="mr-2 hover:underline">{p}</Link>) : "none"],
                ]}
              />
            </div>
          </Section>
          <Section title="Demand and use over time" description="Last 30 days. Wanted is every run that asked for this skill; used is the runs it completed.">
            <QueryView query={runs} rows={3}>
              {() => (
                <ChartContainer config={config} className="h-[260px] w-full">
                  <AreaChart data={series}>
                    <defs>
                      <linearGradient id="skill-req" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--color-requested)" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="var(--color-requested)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="day" tickLine={false} axisLine={false} fontSize={11} interval={4} />
                    <YAxis tickLine={false} axisLine={false} fontSize={11} width={32} allowDecimals={false} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <ChartLegend content={<ChartLegendContent />} />
                    <Area isAnimationActive={!reduce} dataKey="requested" type="monotone" stroke="var(--color-requested)" fill="url(#skill-req)" strokeWidth={2} />
                    <Area isAnimationActive={!reduce} dataKey="completed" type="monotone" stroke="var(--color-completed)" fill="transparent" strokeWidth={2} />
                    <Area isAnimationActive={!reduce} dataKey="escalated" type="monotone" stroke="var(--color-escalated)" fill="transparent" strokeWidth={1.5} strokeDasharray="4 3" />
                  </AreaChart>
                </ChartContainer>
              )}
            </QueryView>
            <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              <Kpi label="Runs, all time" value={total.toLocaleString()} />
              <Kpi label="Completed" value={total ? pct(done / total) : "n/a"} tone={total && done / total < 0.75 ? "warn" : "ok"} />
              <Kpi label="Escalated" value={total ? pct(escalated / total) : "n/a"} tone={escalated ? "warn" : undefined} />
              <Kpi label="Avg cost per run" value={usd(avg((r) => r.costUsd))} hint={`${duration(avg((r) => r.latencyMs))} average`} />
            </div>
          </Section>
        </div>
        <div className="space-y-6">
          <Section title="Skill health">
            <HealthBars s={live} />
          </Section>
          <Section title="Who uses it">
            <ul className="space-y-1.5 text-sm">
              {live.agentIds.map((a) => (
                <li key={a} className="flex items-center justify-between gap-2">
                  <AgentChip id={a} />
                  <span className="text-xs tabular text-muted-foreground">{byAgent.find(([id]) => id === a)?.[1] ?? 0} runs</span>
                </li>
              ))}
            </ul>
          </Section>
          <Section title="Eval suite" description="Runs in a sandbox against recorded cases">
            <KeyValue items={[["Suite", <Mono key="s">{live.evalSuite.id}</Mono>], ["Cases", live.evalSuite.cases], ["Pass rate", pct(live.evalSuite.passRate)]]} />
          </Section>
          {versions.filter((v) => v.branch !== "main").length > 0 && (
            <Section title="Drafts of this skill">
              <ul className="space-y-1 text-xs">
                {versions.filter((v) => v.branch !== "main").map((v) => <li key={v.branch}><Mono>{v.branch}</Mono> · {v.origin}</li>)}
              </ul>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}
