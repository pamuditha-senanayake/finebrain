"use client";

import { ArrowUpRight, ChevronsUp } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo } from "react";
import type { Run } from "@/contracts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, type Column } from "@/components/brain/data-table";
import { ThinkingOrb } from "@/components/brain/motion";
import { PersonChip, useLookup } from "@/components/brain/names";
import { Kpi, Mono, PageHeader, QueryView, Section, Status } from "@/components/brain/primitives";
import { useAgent, useOp, usePolicies, useRuns, useSensors, useSkills, useTemplates } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { dateTime, duration, pct, relTime, usd } from "@/lib/format";

const LADDER = ["trainee", "supervised", "autonomous"] as const;

export function AgentProfile() {
  const { id } = useParams<{ id: string }>();
  const agent = useAgent(id);
  const runs = useRuns({ agentId: id, limit: 2000 });
  const skills = useSkills("main");
  const policies = usePolicies();
  const sensors = useSensors();
  const templates = useTemplates();
  const lookup = useLookup();
  const router = useRouter();
  const { user } = useCurrentUser();
  const promote = useOp<{ agentId: string }>("promoteAgent", { success: "Promotion drafted as a change request" });
  const runColumns: Column<Run>[] = useMemo(
    () => [
      { id: "subject", header: "Run", width: "minmax(200px,2fr)", value: (r) => r.subject, cell: (r) => <span className="truncate">{r.subject}</span> },
      { id: "skill", header: "Skill", width: "minmax(120px,1fr)", value: (r) => r.skill.id, hideOnMobile: true, cell: (r) => <Mono>{r.skill.id} v{r.skill.version}</Mono> },
      { id: "status", header: "Status", width: "110px", value: (r) => r.status, cell: (r) => <Status value={r.status} /> },
      { id: "started", header: "Started", width: "120px", value: (r) => r.startedAt, hideOnMobile: true, cell: (r) => <span className="text-muted-foreground">{dateTime(r.startedAt, lookup.tz)}</span> },
      { id: "latency", header: "Latency", width: "80px", align: "right", value: (r) => r.latencyMs, hideOnMobile: true, cell: (r) => duration(r.latencyMs) },
      { id: "cost", header: "Cost", width: "70px", align: "right", value: (r) => r.costUsd, cell: (r) => usd(r.costUsd) },
    ],
    [lookup.tz],
  );

  return (
    <QueryView query={agent}>
      {(a) => {
        const mySkills = (skills.data ?? []).filter((s) => a.skills.some((r) => r.id === s.id));
        const step = LADDER.indexOf(a.autonomy);
        return (
          <div>
            <PageHeader
              eyebrow={<Link href="/l3" className="hover:underline">Fleet</Link>}
              title={a.name}
              description={a.description}
              actions={
                <div className="flex items-center gap-2">
                  {a.status === "working" && <ThinkingOrb kind={a.workKind} size={18} />}
                  <Status value={a.status} />
                  <Badge variant="outline" className="capitalize">{a.autonomy}</Badge>
                </div>
              }
            />
            <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
              <Kpi label="Task success" value={pct(a.taskSuccess)} />
              <Kpi label="Error rate" value={pct(a.errorRate, 1)} tone={a.errorRate > 0.04 ? "risk" : undefined} />
              <Kpi label="Queue depth" value={a.queueDepth} />
              <Kpi label="Throughput per hour" value={a.throughputPerHour.toFixed(1)} />
              <Kpi label="Cost today" value={usd(a.costTodayUsd)} />
            </div>
            <Tabs defaultValue="job">
              <TabsList>
                <TabsTrigger value="job">Job description</TabsTrigger>
                <TabsTrigger value="runs">Runs</TabsTrigger>
                <TabsTrigger value="training">Academy</TabsTrigger>
              </TabsList>
              <TabsContent value="job" className="mt-3 grid gap-3 lg:grid-cols-2">
                <Section title="What it watches" description="Sensors feeding this agent">
                  <ul className="flex flex-wrap gap-1.5">
                    {a.sensors.length === 0 && <li className="text-xs text-muted-foreground">Reads all L3 runs</li>}
                    {a.sensors.map((s) => (
                      <li key={s}><Badge variant="secondary">{sensors.data?.find((x) => x.id === s)?.name ?? s}</Badge></li>
                    ))}
                  </ul>
                </Section>
                <Section title="How it works" description="Skills and versions on main">
                  <ul className="space-y-1.5 text-sm">
                    {mySkills.map((s) => (
                      <li key={s.id} className="flex items-center justify-between gap-2">
                        <Link href={`/l2/skills/${s.id}`} className="truncate hover:underline">{s.name}</Link>
                        <Mono className="text-muted-foreground">v{s.version} · {pct(s.health.taskSuccess)}</Mono>
                      </li>
                    ))}
                  </ul>
                </Section>
                <Section title="Which rules govern it" description="Policies valid now">
                  <ul className="space-y-1 text-sm">
                    {a.policies.length === 0 && <li className="text-xs text-muted-foreground">No policies</li>}
                    {a.policies.map((p) => {
                      const pol = policies.data?.find((x) => x.key === p && !x.supersededBy && x.branch === "main");
                      return (
                        <li key={p}>
                          <Link href={`/l2/policies/${p}`} className="hover:underline">{pol ? `${pol.name} v${pol.version}` : p}</Link>
                        </li>
                      );
                    })}
                  </ul>
                </Section>
                <Section title="What it may do" description={`Capabilities, access level ${a.accessLevel}`}>
                  <ul className="flex flex-wrap gap-1.5">
                    {a.capabilities.map((c) => (
                      <li key={c}><Mono className="rounded bg-muted px-1.5 py-0.5">{c}</Mono></li>
                    ))}
                  </ul>
                </Section>
                <Section title="What it must return" description="Templates it fills">
                  <ul className="space-y-1 text-sm">
                    {a.templates.map((tId) => (
                      <li key={tId}><Link href="/l3/templates" className="hover:underline">{templates.data?.find((x) => x.id === tId)?.name ?? tId}</Link></li>
                    ))}
                  </ul>
                </Section>
                <Section title="Responsibility">
                  <div className="text-sm">DRI: <PersonChip id={a.dri} /></div>
                </Section>
              </TabsContent>
              <TabsContent value="runs" className="mt-3">
                <QueryView query={runs}>
                  {(rs) => <DataTable label="Runs" data={rs} columns={runColumns} getRowId={(r) => r.id} onRowClick={(r) => router.push(`/l3/runs/${r.id}`)} initialSort={{ id: "started", desc: true }} height={520} />}
                </QueryView>
              </TabsContent>
              <TabsContent value="training" className="mt-3 grid gap-3 lg:grid-cols-[1fr_1.4fr]">
                <Section title="Autonomy level" description="Each promotion follows the criticality matrix: to supervised is C2, to autonomous is C3.">
                  <ol className="mb-4 flex items-center gap-2" aria-label="Autonomy ladder">
                    {LADDER.map((l, i) => (
                      <li key={l} className={`flex-1 rounded-lg border p-2 text-center text-xs capitalize ${i <= step ? "border-primary/50 bg-primary/10 font-medium" : "text-muted-foreground"}`} aria-current={i === step ? "step" : undefined}>
                        {l}
                      </li>
                    ))}
                  </ol>
                  <Button size="sm" variant="outline" disabled={step === 2 || !user || user.tier === "L3" || promote.isPending} onClick={() => promote.mutate({ agentId: a.id })}>
                    <ChevronsUp /> Propose promotion
                  </Button>
                  {user?.tier === "L3" && <p className="mt-2 text-xs text-muted-foreground">Promotions are proposed by L2 stewards.</p>}
                </Section>
                <Section title="Training history">
                  <ol className="space-y-2 text-sm">
                    {[...a.training].reverse().map((tr, i) => (
                      <li key={i} className="flex gap-3">
                        <span className="w-24 shrink-0 text-xs text-muted-foreground">{relTime(tr.at)}</span>
                        <span>{tr.event} <span className="text-xs text-muted-foreground">· {lookup.name(tr.by)}</span></span>
                      </li>
                    ))}
                  </ol>
                  <Link href="/l2/skills" className="mt-3 inline-flex items-center gap-1 text-xs text-primary hover:underline">
                    Agent Academy and eval suites <ArrowUpRight className="size-3" />
                  </Link>
                </Section>
              </TabsContent>
            </Tabs>
          </div>
        );
      }}
    </QueryView>
  );
}
