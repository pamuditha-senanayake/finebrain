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
      { id: "name", header: "Sensor", width: "minmax(200px,1.5fr)", value: (s) => s.name, cell: (s) => <div className="min-w-0"><div className="truncate font-medium">{s.name}</div><div className="mt-0.5 truncate text-[11px] text-muted-foreground">{s.source} · {lookup.cluster(s.clusterId)}</div></div> },
      { id: "workflow", header: "Workflow", width: "minmax(160px,1.2fr)", value: (s) => index.of("sensor", s.id).join(", "), cell: (s) => { const w = index.of("sensor", s.id); return w.length ? <span className="truncate" title={w.join(", ")}>{w[0]}{w.length > 1 && <span className="text-muted-foreground"> +{w.length - 1}</span>}</span> : <span className="text-muted-foreground">—</span>; } },
      { id: "health", header: "Health", width: "84px", value: (s) => s.health, cell: (s) => <Status value={s.health} /> },
      { id: "subs", header: "Subscribers", width: "minmax(150px,1.1fr)", value: (s) => s.subscribers.length, hideOnMobile: true, cell: (s) => <div className="min-w-0"><div className="truncate text-xs" title={s.subscribers.map((x) => lookup.name(x)).join(", ")}>{s.subscribers.map((x) => lookup.name(x)).join(", ") || "none"}</div><Mono className="mt-0.5 block truncate text-[11px] text-muted-foreground">{s.scopes.join(", ")}</Mono></div> },
      { id: "pd", header: "Personal", width: "104px", value: (s) => (s.personalData ? 1 : 0), cell: (s) => (s.personalData ? <StatusChip tone="warn">yes, masked</StatusChip> : <span className="text-muted-foreground">no</span>) },
      { id: "last", header: "Last event", width: "110px", value: (s) => s.lastEventAt, hideOnMobile: true, cell: (s) => <div><div className="text-muted-foreground">{relTime(s.lastEventAt)}</div><div className="mt-0.5 text-[11px] text-muted-foreground">keeps {s.retentionDays}d</div></div> },
    ],
    [lookup, index],
  );
  return (
    <div>
      <PageHeader title="Sensors and connections" description="Every connected system per cluster with health, subscribers, scopes, retention and a personal data flag." />
      <QueryView query={sensors}>
        {(ss) => (
          <DataTable
            rowHeight={58}
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
