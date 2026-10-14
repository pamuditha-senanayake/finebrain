"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { Run } from "@/contracts";
import { Button } from "@/components/ui/button";
import { CategoryFilter, countBy } from "@/components/brain/category-filter";
import { DataTable, type Column } from "@/components/brain/data-table";
import { AgentChip, useLookup } from "@/components/brain/names";
import { KeyValue, Mono, PageHeader, QueryView, Section, Status } from "@/components/brain/primitives";
import { useRuns } from "@/lib/api/hooks";
import { dateTime, duration, usd } from "@/lib/format";
import { useUi } from "@/lib/store";
import { RunInput, useRunContext } from "./run-context";

export function RunsExplorer() {
  const runs = useRuns();
  const lookup = useLookup();
  const ctx = useRunContext();
  const clusterId = useUi((s) => s.clusterId);
  const [actor, setActor] = useState("all");
  const [status, setStatus] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const base = useMemo(() => (runs.data ?? []).filter((r) => clusterId === "all" || r.clusterId === clusterId), [runs.data, clusterId]);
  const data = useMemo(() => base.filter((r) => (actor === "all" || ctx.actorOf(r) === actor) && (status === "all" || r.status === status)), [base, actor, status, ctx]);
  const selected = base.find((r) => r.id === selectedId) ?? null;
  const columns: Column<Run>[] = useMemo(
    () => [
      { id: "started", header: "Started", width: "120px", value: (r) => r.startedAt, cell: (r) => <span className="text-muted-foreground">{dateTime(r.startedAt, lookup.tz)}</span> },
      { id: "actor", header: "Actor", width: "minmax(130px,1fr)", value: (r) => ctx.actorOf(r), cell: (r) => <span className="truncate font-medium">{ctx.actorOf(r)}</span> },
      { id: "subject", header: "Run", width: "minmax(200px,2fr)", value: (r) => r.subject, cell: (r) => <span className="truncate">{r.subject}</span> },
      { id: "agent", header: "Agent", width: "minmax(140px,1fr)", value: (r) => lookup.name(r.agentId), hideOnMobile: true, cell: (r) => <AgentChip id={r.agentId} link={false} /> },
      { id: "skill", header: "Skill", width: "minmax(130px,1fr)", value: (r) => r.skill.id, hideOnMobile: true, cell: (r) => <Mono className="truncate">{r.skill.id} v{r.skill.version}</Mono> },
      { id: "status", header: "Status", width: "120px", value: (r) => r.status, cell: (r) => <Status value={r.status} /> },
      { id: "latency", header: "Latency", width: "80px", align: "right", value: (r) => r.latencyMs, hideOnMobile: true, cell: (r) => duration(r.latencyMs) },
      { id: "cost", header: "Cost", width: "70px", align: "right", value: (r) => r.costUsd, cell: (r) => usd(r.costUsd) },
    ],
    [lookup, ctx],
  );
  return (
    <div>
      <PageHeader title="Agent running history" description="Every run any agent made, and who it acted for. Filter by actor when a customer reports an issue; open a row to read the input and conversation." />
      <QueryView query={runs}>
        {() => (
          <div className={selected ? "grid gap-4 xl:grid-cols-[minmax(0,1fr)_400px]" : undefined}>
            <DataTable
              label="Agent running history"
              data={data}
              columns={columns}
              getRowId={(r) => r.id}
              onRowClick={(r) => setSelectedId(r.id)}
              rowClassName={(r) => (r.id === selectedId ? "bg-primary/10" : undefined)}
              initialSort={{ id: "started", desc: true }}
              height="calc(100dvh - 240px)"
              searchPlaceholder="Search actor, run, agent"
              toolbar={
                <>
                  <CategoryFilter label="Filter by actor" allLabel="All actors" value={actor} onChange={setActor} options={countBy(base, ctx.actorOf)} className="w-[200px] text-xs normal-case" />
                  <CategoryFilter label="Filter by status" allLabel="All statuses" value={status} onChange={setStatus} options={countBy(base, (r) => r.status)} className="w-[170px] text-xs" />
                </>
              }
            />
            {selected && (
              <aside className="min-w-0 space-y-3 xl:sticky xl:top-16 xl:max-h-[calc(100dvh-5rem)] xl:self-start xl:overflow-auto" aria-label="Run details">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="truncate text-sm font-semibold">{selected.subject}</h2>
                    <div className="mt-1 flex items-center gap-2"><Status value={selected.status} /><span className="text-xs text-muted-foreground">{dateTime(selected.startedAt, lookup.tz)}</span></div>
                  </div>
                  <Button size="icon-sm" variant="ghost" onClick={() => setSelectedId(null)} aria-label="Close details"><X /></Button>
                </div>
                <RunInput run={selected} conversation={ctx.conversationOf(selected)} actor={ctx.actorOf(selected)} />
                <Section title="Run">
                  <KeyValue items={[["Agent", <AgentChip key="a" id={selected.agentId} />], ["Skill", <Mono key="s">{selected.skill.id} v{selected.skill.version}</Mono>], ["Latency", duration(selected.latencyMs)], ["Cost", usd(selected.costUsd)], ["Human touch", selected.humanTouch ? "yes" : "no"]]} />
                  <Button asChild size="sm" className="mt-3 w-full"><Link href={`/l3/runs/${selected.id}`}>Open the full trace</Link></Button>
                </Section>
              </aside>
            )}
          </div>
        )}
      </QueryView>
    </div>
  );
}
