"use client";

import { LayoutGrid, List } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { Agent } from "@/contracts";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { CategoryFilter, WorkflowFilter, countBy, countByMany } from "@/components/brain/category-filter";
import { DataTable, type Column } from "@/components/brain/data-table";
import { IdleDot, ThinkingOrb } from "@/components/brain/motion";
import { useLookup } from "@/components/brain/names";
import { Kpi, PageHeader, QueryView, Status } from "@/components/brain/primitives";
import { useAgents } from "@/lib/api/hooks";
import { num, pct, usd } from "@/lib/format";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";
import { useWorkflowIndex } from "@/lib/workflow-index";

export function Fleet() {
  const agents = useAgents();
  const clusterId = useUi((s) => s.clusterId);
  const [view, setView] = useState<"table" | "grid">("table");
  const router = useRouter();
  const lookup = useLookup();
  const index = useWorkflowIndex();
  const [category, setCategory] = useState("all");
  const [wf, setWf] = useState("all");
  const catOf = (a: Agent) => index.category("agent", a.id);
  const wfOf = (a: Agent) => index.of("agent", a.id);
  const scoped = useMemo(() => (agents.data ?? []).filter((a) => clusterId === "all" || a.clusterId === clusterId), [agents.data, clusterId]);
  const data = scoped.filter((a) => (category === "all" || catOf(a) === category) && (wf === "all" || wfOf(a).includes(wf)));
  const filters = (
    <>
      <CategoryFilter label="Filter by category" allLabel="All categories" value={category} onChange={setCategory} options={countBy(scoped, catOf)} />
      <WorkflowFilter value={wf} onChange={setWf} options={countByMany(scoped, wfOf)} />
    </>
  );
  const columns: Column<Agent>[] = useMemo(
    () => [
      { id: "name", header: "Agent", width: "minmax(200px,1.6fr)", value: (a) => a.name, cell: (a) => (
        <span className="flex min-w-0 items-center gap-2.5">
          {a.status === "working" ? <ThinkingOrb kind={a.workKind} size={12} /> : <IdleDot tone={a.status === "blocked" || a.status === "error" ? "risk" : "neutral"} />}
          <span className="min-w-0">
            <span className="block truncate font-medium">{a.name}</span>
            <span className="block truncate text-[11px] text-muted-foreground">{a.kind === "supervisor" ? "L2 supervisor" : "L3 worker"} · {lookup.cluster(a.clusterId)}</span>
          </span>
        </span>
      ) },
      { id: "workflow", header: "Workflow", width: "minmax(170px,1.3fr)", value: (a) => wfOf(a).join(", "), hideOnMobile: true, cell: (a) => { const w = wfOf(a); return (
        <span className="block min-w-0">
          <span className="block truncate" title={w.join(", ")}>{w[0] ?? "—"}{w.length > 1 && <span className="text-muted-foreground"> +{w.length - 1}</span>}</span>
          <span className="block truncate text-[11px] capitalize text-muted-foreground">{catOf(a)}</span>
        </span>
      ); } },
      { id: "status", header: "Status", width: "96px", value: (a) => a.status, cell: (a) => <Status value={a.status} /> },
      { id: "autonomy", header: "Autonomy", width: "100px", value: (a) => a.autonomy, hideOnMobile: true, cell: (a) => <span className="capitalize">{a.autonomy}</span> },
      { id: "queue", header: "Queue", width: "64px", align: "right", value: (a) => a.queueDepth, cell: (a) => a.queueDepth },
      { id: "tput", header: "Per hour", width: "72px", align: "right", value: (a) => a.throughputPerHour, hideOnMobile: true, cell: (a) => a.throughputPerHour.toFixed(1) },
      { id: "errors", header: "Errors", width: "64px", align: "right", value: (a) => a.errorRate, hideOnMobile: true, cell: (a) => <span className={cn(a.errorRate > 0.04 && "text-risk")}>{pct(a.errorRate, 1)}</span> },
      { id: "cost", header: "Cost today", width: "84px", align: "right", value: (a) => a.costTodayUsd, hideOnMobile: true, cell: (a) => usd(a.costTodayUsd) },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lookup, index],
  );
  const working = data.filter((a) => a.status === "working").length;
  return (
    <div>
      <PageHeader title="Fleet" description="Every agent, live. Agents work through APIs; this view is for the people who watch them and step in." />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Kpi label="Working now" value={`${working} / ${data.length}`} />
        <Kpi label="Queue depth" value={num(data.reduce((s, a) => s + a.queueDepth, 0))} />
        <Kpi label="Throughput per hour" value={data.reduce((s, a) => s + a.throughputPerHour, 0).toFixed(0)} />
        <Kpi label="Blocked or erroring" value={data.filter((a) => a.status === "blocked" || a.status === "error").length} tone={data.some((a) => a.status === "blocked" || a.status === "error") ? "risk" : undefined} />
        <Kpi label="Cost today" value={usd(data.reduce((s, a) => s + a.costTodayUsd, 0))} />
      </div>
      <QueryView query={agents}>
        {() =>
          view === "table" ? (
            <DataTable
              rowHeight={58}
              label="Agents"
              data={data}
              columns={columns}
              getRowId={(a) => a.id}
              onRowClick={(a) => router.push(`/l3/agents/${a.id}`)}
              initialSort={{ id: "status", desc: true }}
              height="calc(100dvh - 330px)"
              searchPlaceholder="Filter agents"
              toolbar={<>{filters}<ViewToggle view={view} setView={setView} /></>}
            />
          ) : (
            <div>
              <div className="mb-2 flex flex-wrap items-center justify-end gap-2">
                {filters}
                <ViewToggle view={view} setView={setView} />
              </div>
              <ul className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-2" aria-label="Agents">
                {data.map((a) => (
                  <li key={a.id}>
                    <Link href={`/l3/agents/${a.id}`} className="block rounded-xl border bg-card p-3 text-sm hover:border-primary/40">
                      <div className="flex items-center gap-2">
                        {a.status === "working" ? <ThinkingOrb kind={a.workKind} /> : <IdleDot tone={a.status === "blocked" ? "risk" : "neutral"} />}
                        <span className="truncate font-medium">{a.name}</span>
                      </div>
                      <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                        <Status value={a.status} />
                        <span>queue {a.queueDepth}</span>
                        <span>{usd(a.costTodayUsd)}</span>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )
        }
      </QueryView>
    </div>
  );
}

function ViewToggle({ view, setView }: { view: "table" | "grid"; setView: (v: "table" | "grid") => void }) {
  return (
    <ToggleGroup type="single" value={view} onValueChange={(v) => v && setView(v as "table" | "grid")} variant="outline" size="sm" aria-label="View">
      <ToggleGroupItem value="table" aria-label="Table">
        <List />
      </ToggleGroupItem>
      <ToggleGroupItem value="grid" aria-label="Grid">
        <LayoutGrid />
      </ToggleGroupItem>
    </ToggleGroup>
  );
}
