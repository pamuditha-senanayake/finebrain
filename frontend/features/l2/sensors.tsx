"use client";

import { Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { WorkflowFilter, countByMany } from "@/components/brain/category-filter";
import { useWorkflowIndex } from "@/lib/workflow-index";
import type { Sensor } from "@/contracts";
import { DataTable, type Column } from "@/components/brain/data-table";
import { useLookup } from "@/components/brain/names";
import { Mono, PageHeader, QueryView, Status, StatusChip } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { ConnectorPicker } from "@/features/connect/connector-picker";
import { ConnectorsList } from "@/features/connect/connectors-list";
import { SensorSheet } from "@/features/connect/details";
import { Switch } from "@/components/ui/switch";
import { useConnect } from "@/lib/connect/store";
import { useSensors } from "@/lib/api/hooks";
import { relTime } from "@/lib/format";

export function Sensors() {
  const sensors = useSensors();
  const lookup = useLookup();
  const index = useWorkflowIndex();
  const [wf, setWf] = useState("all");
  const [adding, setAdding] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const sensorsOff = useConnect((s) => s.sensorsOff);
  const setSensorOn = useConnect((s) => s.setSensorOn);
  const columns: Column<Sensor>[] = useMemo(
    () => [
      { id: "name", header: "Sensor", width: "minmax(200px,1.5fr)", value: (s) => s.name, cell: (s) => <div className="min-w-0"><div className="truncate font-medium">{s.name}</div><div className="mt-0.5 truncate text-[11px] text-muted-foreground">{s.source} · {lookup.cluster(s.clusterId)}</div></div> },
      { id: "workflow", header: "Workflow", width: "minmax(160px,1.2fr)", value: (s) => index.of("sensor", s.id).join(", "), cell: (s) => { const w = index.of("sensor", s.id); return w.length ? <span className="truncate" title={w.join(", ")}>{w[0]}{w.length > 1 && <span className="text-muted-foreground"> +{w.length - 1}</span>}</span> : <span className="text-muted-foreground">—</span>; } },
      { id: "health", header: "Health", width: "84px", value: (s) => (sensorsOff[s.id] ? "paused" : s.health), cell: (s) => <Status value={sensorsOff[s.id] ? "paused" : s.health} /> },
      {
        id: "on",
        header: "On",
        width: "64px",
        value: (s) => (sensorsOff[s.id] ? 0 : 1),
        // The switch sits inside a clickable row, so its click must not also open the details.
        cell: (s) => <span onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}><Switch checked={!sensorsOff[s.id]} onCheckedChange={(v) => setSensorOn(s.id, v)} aria-label={`${s.name} ${sensorsOff[s.id] ? "off" : "on"}`} /></span>,
      },
      { id: "subs", header: "Subscribers", width: "minmax(150px,1.1fr)", value: (s) => s.subscribers.length, hideOnMobile: true, cell: (s) => <div className="min-w-0"><div className="truncate text-xs" title={s.subscribers.map((x) => lookup.name(x)).join(", ")}>{s.subscribers.map((x) => lookup.name(x)).join(", ") || "none"}</div><Mono className="mt-0.5 block truncate text-[11px] text-muted-foreground">{s.scopes.join(", ")}</Mono></div> },
      { id: "pd", header: "Personal", width: "104px", value: (s) => (s.personalData ? 1 : 0), cell: (s) => (s.personalData ? <StatusChip tone="warn">yes, masked</StatusChip> : <span className="text-muted-foreground">no</span>) },
      { id: "last", header: "Last event", width: "110px", value: (s) => s.lastEventAt, hideOnMobile: true, cell: (s) => <div><div className="text-muted-foreground">{relTime(s.lastEventAt)}</div><div className="mt-0.5 text-[11px] text-muted-foreground">keeps {s.retentionDays}d</div></div> },
    ],
    [lookup, index, sensorsOff, setSensorOn],
  );
  return (
    <div>
      <PageHeader
        title="Sensors and connections"
        description="Every connected system and what it feeds the brain."
        actions={
          <>
            <Button asChild variant="ghost"><Link href="/l1/setup"><Sparkles /> Guided setup</Link></Button>
            <Button onClick={() => setAdding(true)}><Plus /> Add connector</Button>
          </>
        }
      />
      <ConnectorPicker open={adding} onOpenChange={setAdding} />
      <ConnectorsList
        className="mb-10"
        empty={
          <div className="flex flex-col items-start gap-4 py-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[15px] text-muted-foreground">None yet. Link Gmail, Slack, GitHub, a database or any MCP server.</p>
            <Button variant="outline" onClick={() => setAdding(true)}><Plus /> Add connector</Button>
          </div>
        }
      />
      <h2 className="mb-4 text-[15px] font-semibold tracking-tight">Sensors</h2>
      <QueryView query={sensors}>
        {(ss) => (
          <DataTable
            rowHeight={58}
            label="Sensors"
            data={wf === "all" ? ss : ss.filter((x) => index.of("sensor", x.id).includes(wf))}
            columns={columns}
            getRowId={(x) => x.id}
            onRowClick={(x) => setOpenId(x.id)}
            initialSort={{ id: "health", desc: false }}
            height="calc(100dvh - 240px)"
            toolbar={<WorkflowFilter value={wf} onChange={setWf} options={countByMany(ss, (x) => index.of("sensor", x.id))} />}
          />
        )}
      </QueryView>
      <SensorSheet sensor={sensors.data?.find((x) => x.id === openId) ?? null} onClose={() => setOpenId(null)} />
    </div>
  );
}
