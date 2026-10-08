"use client";

import { useRouter } from "next/navigation";
import { useMemo } from "react";
import type { Run } from "@/contracts";
import { DataTable, type Column } from "@/components/brain/data-table";
import { AgentChip, useLookup } from "@/components/brain/names";
import { Mono, PageHeader, QueryView, Status } from "@/components/brain/primitives";
import { useRuns } from "@/lib/api/hooks";
import { dateTime, duration, usd } from "@/lib/format";
import { useUi } from "@/lib/store";

export function RunsExplorer() {
  const runs = useRuns();
  const router = useRouter();
  const lookup = useLookup();
  const clusterId = useUi((s) => s.clusterId);
  const data = useMemo(() => (runs.data ?? []).filter((r) => clusterId === "all" || r.clusterId === clusterId), [runs.data, clusterId]);
  const columns: Column<Run>[] = useMemo(
    () => [
      { id: "started", header: "Started", width: "120px", value: (r) => r.startedAt, cell: (r) => <span className="text-muted-foreground">{dateTime(r.startedAt, lookup.tz)}</span> },
      { id: "subject", header: "Run", width: "minmax(200px,2fr)", value: (r) => r.subject, cell: (r) => <span className="truncate">{r.subject}</span> },
      { id: "agent", header: "Agent", width: "minmax(140px,1fr)", value: (r) => lookup.name(r.agentId), hideOnMobile: true, cell: (r) => <AgentChip id={r.agentId} /> },
      { id: "skill", header: "Skill", width: "minmax(130px,1fr)", value: (r) => r.skill.id, hideOnMobile: true, cell: (r) => <Mono className="truncate">{r.skill.id} v{r.skill.version}</Mono> },
      { id: "status", header: "Status", width: "120px", value: (r) => r.status, cell: (r) => <Status value={r.status} /> },
      { id: "latency", header: "Latency", width: "80px", align: "right", value: (r) => r.latencyMs, hideOnMobile: true, cell: (r) => duration(r.latencyMs) },
      { id: "cost", header: "Cost", width: "70px", align: "right", value: (r) => r.costUsd, cell: (r) => usd(r.costUsd) },
    ],
    [lookup],
  );
  return (
    <div>
      <PageHeader title="Runs" description="Every run any agent made. Open one to see its full trace." />
      <QueryView query={runs}>
        {() => <DataTable label="Runs" data={data} columns={columns} getRowId={(r) => r.id} onRowClick={(r) => router.push(`/l3/runs/${r.id}`)} initialSort={{ id: "started", desc: true }} height="calc(100dvh - 240px)" searchPlaceholder="Filter runs" />}
      </QueryView>
    </div>
  );
}
