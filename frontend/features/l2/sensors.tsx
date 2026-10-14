"use client";

import { useMemo, useState } from "react";
import { WorkflowFilter, countByMany } from "@/components/brain/category-filter";
import { useWorkflowIndex } from "@/lib/workflow-index";
import type { Sensor } from "@/contracts";
import { DataTable, type Column } from "@/components/brain/data-table";
import { useLookup } from "@/components/brain/names";
import { Mono, PageHeader, QueryView, Status, StatusChip } from "@/components/brain/primitives";
import { useSensors } from "@/lib/api/hooks";
import { relTime } from "@/lib/format";

export function Sensors() {
  const sensors = useSensors();
  const lookup = useLookup();
  const index = useWorkflowIndex();
  const [wf, setWf] = useState("all");
  const columns: Column<Sensor>[] = useMemo(
    () => [
      { id: "name", header: "Sensor", width: "minmax(180px,1.4fr)", value: (s) => s.name, cell: (s) => <span className="font-medium">{s.name}</span> },
      { id: "workflow", header: "Workflow", width: "minmax(160px,1.2fr)", value: (s) => index.of("sensor", s.id).join(", "), cell: (s) => { const w = index.of("sensor", s.id); return w.length ? <span className="truncate" title={w.join(", ")}>{w[0]}{w.length > 1 && <span className="text-muted-foreground"> +{w.length - 1}</span>}</span> : <span className="text-muted-foreground">none</span>; } },
      { id: "source", header: "Source", width: "minmax(140px,1fr)", value: (s) => s.source, hideOnMobile: true, cell: (s) => <span className="truncate text-muted-foreground">{s.source}</span> },
      { id: "cluster", header: "Cluster", width: "minmax(120px,1fr)", value: (s) => lookup.cluster(s.clusterId), hideOnMobile: true, cell: (s) => <span className="truncate text-muted-foreground">{lookup.cluster(s.clusterId)}</span> },
      { id: "health", header: "Health", width: "84px", value: (s) => s.health, cell: (s) => <Status value={s.health} /> },
      { id: "subs", header: "Subscribers", width: "minmax(120px,1fr)", value: (s) => s.subscribers.length, hideOnMobile: true, cell: (s) => <span className="truncate text-xs">{s.subscribers.map((x) => lookup.name(x)).join(", ") || "none"}</span> },
      { id: "scopes", header: "Scopes", width: "minmax(120px,1fr)", value: (s) => s.scopes.join(","), hideOnMobile: true, cell: (s) => <Mono className="truncate">{s.scopes.join(", ")}</Mono> },
      { id: "pd", header: "Personal data", width: "100px", value: (s) => (s.personalData ? 1 : 0), cell: (s) => (s.personalData ? <StatusChip tone="warn">yes, masked</StatusChip> : <span className="text-muted-foreground">no</span>) },
      { id: "retention", header: "Retention", width: "84px", align: "right", value: (s) => s.retentionDays, hideOnMobile: true, cell: (s) => `${s.retentionDays}d` },
      { id: "last", header: "Last event", width: "100px", value: (s) => s.lastEventAt, hideOnMobile: true, cell: (s) => <span className="text-muted-foreground">{relTime(s.lastEventAt)}</span> },
    ],
    [lookup, index],
  );
  return (
    <div>
      <PageHeader title="Sensors and connections" description="Every connected system per cluster with health, subscribers, scopes, retention and a personal data flag." />
      <QueryView query={sensors}>
        {(ss) => (
          <DataTable
            label="Sensors"
            data={wf === "all" ? ss : ss.filter((x) => index.of("sensor", x.id).includes(wf))}
            columns={columns}
            getRowId={(x) => x.id}
            initialSort={{ id: "health", desc: false }}
            height="calc(100dvh - 240px)"
            toolbar={<WorkflowFilter value={wf} onChange={setWf} options={countByMany(ss, (x) => index.of("sensor", x.id))} />}
          />
        )}
      </QueryView>
    </div>
  );
}
