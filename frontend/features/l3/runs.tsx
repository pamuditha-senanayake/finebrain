"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import * as C from "@/contracts";
import type { Run } from "@/contracts";
import { Button } from "@/components/ui/button";
import { CategoryFilter } from "@/components/brain/category-filter";
import { FilterChips } from "@/components/brain/filter-chips";
import { PagedTable, type PagedColumn } from "@/components/brain/paged-table";
import { AgentChip, useLookup } from "@/components/brain/names";
import { EmptyState, KeyValue, Mono, PageHeader, Section, Status } from "@/components/brain/primitives";
import { usePagedList } from "@/lib/api/paged";
import { useFocusTarget } from "@/lib/focus";
import { dateTime, duration, usd } from "@/lib/format";
import { useUi } from "@/lib/store";
import { RunInput, useRunContext } from "./run-context";

export function RunsExplorer() {
  const lookup = useLookup();
  const ctx = useRunContext();
  const clusterId = useUi((s) => s.clusterId);
  const focus = useFocusTarget();
  const aroundId = focus?.kind === "run" ? focus.id : undefined;
  const list = usePagedList("runs", C.Run, { around: aroundId });
  const [picked, setSelected] = useState<Run | null | undefined>(undefined);
  useEffect(() => list.setFilter("clusterId", clusterId === "all" ? null : clusterId), [clusterId]); // eslint-disable-line react-hooks/exhaustive-deps
  // A focus link also opens the run's detail, once its row has arrived; picking or closing a row after that wins.
  const landed = aroundId && list.position !== null ? list.rowAt(list.position) : undefined;
  const selected = picked !== undefined ? picked : landed && landed.id === aroundId ? landed : null;
  const columns: PagedColumn<Run>[] = useMemo(
    () => [
      { id: "started", header: "Started", width: "120px", sortKey: "startedAt", cell: (r) => <span className="text-muted-foreground">{dateTime(r.startedAt, lookup.tz)}</span> },
      { id: "subject", header: "Run", width: "minmax(220px,2.4fr)", sortKey: "subject", cell: (r) => <span className="truncate">{r.subject}</span> },
      { id: "agent", header: "Agent", width: "minmax(140px,1fr)", hideOnMobile: true, cell: (r) => <AgentChip id={r.agentId} link={false} /> },
      { id: "skill", header: "Skill", width: "minmax(130px,1fr)", hideOnMobile: true, cell: (r) => <Mono className="truncate">{r.skill.id} v{r.skill.version}</Mono> },
      { id: "status", header: "Status", width: "120px", sortKey: "status", cell: (r) => <Status value={r.status} /> },
      { id: "latency", header: "Latency", width: "80px", align: "right", sortKey: "latencyMs", hideOnMobile: true, cell: (r) => duration(r.latencyMs) },
      { id: "cost", header: "Cost", width: "70px", align: "right", sortKey: "costUsd", cell: (r) => usd(r.costUsd) },
    ],
    [lookup],
  );
  const options = (field: string) => Object.entries(list.facets[field] ?? {}).map(([value, count]) => ({ value, count })).sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
  const shown = Object.fromEntries(Object.entries(list.filters).filter(([field]) => field !== "clusterId"));
  return (
    <div>
      <PageHeader title="Agent running history" description="Every run any agent made, and who it acted for. Search for a run, then step through the matches; open a row to read the input and conversation." />
      {list.error ? (
        <EmptyState title="Could not load runs" />
      ) : (
        <div className={selected ? "grid gap-4 xl:grid-cols-[minmax(0,1fr)_400px]" : undefined}>
          <PagedTable
            label="Agent running history"
            list={list}
            columns={columns}
            focusKind="run"
            focusId={aroundId}
            onRowClick={setSelected}
            rowClassName={(r) => (r.id === selected?.id ? "bg-primary/10" : undefined)}
            height="calc(100dvh - 260px)"
            searchPlaceholder="Search runs"
            below={<FilterChips filters={shown} labels={{ status: "Status", agentId: "Agent", actor: "Actor" }} onRemove={(f) => list.setFilter(f, null)} onClear={list.clearFilters} />}
            toolbar={
              <>
                {options("actor").length > 0 && <CategoryFilter label="Filter by actor" allLabel="All actors" value={list.filters.actor ?? "all"} onChange={(v) => list.setFilter("actor", v === "all" ? null : v)} options={options("actor")} className="w-[200px] text-xs normal-case" />}
                <CategoryFilter label="Filter by agent" allLabel="All agents" value={list.filters.agentId ?? "all"} onChange={(v) => list.setFilter("agentId", v === "all" ? null : v)} options={options("agentId")} labelOf={lookup.name} className="w-[190px] text-xs" />
                <CategoryFilter label="Filter by status" allLabel="All statuses" value={list.filters.status ?? "all"} onChange={(v) => list.setFilter("status", v === "all" ? null : v)} options={options("status")} className="w-[170px] text-xs" />
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
                  <Button size="icon-sm" variant="ghost" onClick={() => setSelected(null)} aria-label="Close details"><X /></Button>
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
    </div>
  );
}
