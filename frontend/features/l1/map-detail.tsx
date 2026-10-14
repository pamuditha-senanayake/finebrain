"use client";

import { ArrowUpRight, X } from "lucide-react";
import Link from "next/link";
import type { BrainMap } from "@/contracts";
import { Button } from "@/components/ui/button";
import { PersonChip } from "@/components/brain/names";
import { CritBadge, Status, StatusChip } from "@/components/brain/primitives";
import { money, pct, usd } from "@/lib/format";
import { KIND_COLOR } from "@/lib/studio/graph";
import { KIND_LABEL, KIND_PLURAL, MEMBER_ORDER } from "@/lib/studio/spec";
import { CLUSTER_PALETTE, type MapSelection } from "./brain-map";

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-surface px-2 py-1.5">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className="text-sm font-semibold tabular">{value}</div>
    </div>
  );
}

/** What was clicked on the map, with the way into Workflow Studio to change it. */
export function MapDetail({ map, selection, currency, onSelect, onClose }: { map: BrainMap; selection: MapSelection; currency: string; onSelect: (s: MapSelection) => void; onClose: () => void }) {
  const cluster = selection.kind === "cluster" ? map.clusters.find((c) => c.id === selection.id) : null;
  const wf = selection.kind === "workflow" ? map.workflows.find((w) => w.id === selection.id) : selection.kind === "item" ? map.workflows.find((w) => w.id === selection.workflowId) : null;
  const item = selection.kind === "item" ? wf?.items.find((i) => i.id === selection.id) : null;
  const color = (clusterId: string) => CLUSTER_PALETTE[Math.max(0, map.clusters.findIndex((c) => c.id === clusterId)) % CLUSTER_PALETTE.length];

  return (
    <section className="flex max-h-full w-full flex-col overflow-hidden rounded-2xl border bg-card/95 shadow-lg backdrop-blur" aria-label="Selection details">
      <header className="flex items-start gap-2 border-b px-3 py-2.5">
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: item ? KIND_COLOR[item.kind] : color(cluster?.id ?? wf?.clusterId ?? "") }}>
            {item ? KIND_LABEL[item.kind] : cluster ? "Cluster" : "Workflow"}
          </div>
          <h2 className="truncate text-sm font-semibold">{item?.name ?? wf?.name ?? cluster?.name}</h2>
        </div>
        <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close details">
          <X />
        </Button>
      </header>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3 text-xs">
        {cluster && (
          <>
            <p className="text-muted-foreground">{cluster.description}</p>
            <div className="flex flex-wrap items-center gap-1.5">
              <Status value={cluster.status} />
              {cluster.dri && <><span className="text-muted-foreground">DRI</span> <PersonChip id={cluster.dri} /></>}
            </div>
            {cluster.kpi && (
              <div className="grid grid-cols-2 gap-1.5">
                <Metric label="Autonomy" value={pct(cluster.kpi.autonomyRate)} />
                <Metric label="Escalations" value={pct(cluster.kpi.escalationRate, 1)} />
                <Metric label="Runs, 24h" value={cluster.kpi.runs24h} />
                <Metric label="Health" value={cluster.health} />
                <Metric label="Money at stake" value={money(cluster.kpi.moneyAtStakeMinor, currency, { compact: true })} />
                <Metric label="Cost per task" value={usd(cluster.kpi.costPerResolvedUsd)} />
              </div>
            )}
            <div>
              <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Workflows</div>
              <ul className="space-y-0.5">
                {map.workflows.filter((w) => w.clusterId === cluster.id).map((w) => (
                  <li key={w.id}>
                    <button type="button" className="flex min-h-7 w-full items-center gap-2 rounded-md px-1.5 text-left hover:bg-accent" onClick={() => onSelect({ kind: "workflow", id: w.id })}>
                      <span className="min-w-0 flex-1 truncate">{w.name}</span>
                      {w.health.breaks > 0 && <StatusChip tone="risk" className="h-4 px-1.5 text-[10px]">{w.health.breaks} break{w.health.breaks === 1 ? "" : "s"}</StatusChip>}
                      <span className="text-[10px] text-muted-foreground">{w.items.length}</span>
                    </button>
                  </li>
                ))}
                {!map.workflows.some((w) => w.clusterId === cluster.id) && <li className="text-muted-foreground">None yet.</li>}
              </ul>
            </div>
          </>
        )}
        {wf && !item && (
          <>
            <p className="text-muted-foreground">{wf.description}</p>
            <div className="flex flex-wrap items-center gap-1.5">
              <Status value={wf.status} />
              <CritBadge level={wf.criticality} />
              {wf.health.breaks > 0 ? <StatusChip tone="risk">{wf.health.breaks} break{wf.health.breaks === 1 ? "" : "s"}</StatusChip> : <StatusChip tone="ok">healthy</StatusChip>}
              {wf.health.warnings > 0 && <StatusChip tone="warn">{wf.health.warnings} warning{wf.health.warnings === 1 ? "" : "s"}</StatusChip>}
            </div>
            <div className="flex items-center gap-1.5"><span className="text-muted-foreground">DRI</span> <PersonChip id={wf.dri} /></div>
            {MEMBER_ORDER.map((k) => {
              const list = wf.items.filter((i) => i.kind === k);
              if (!list.length) return null;
              return (
                <div key={k}>
                  <div className="mb-0.5 flex items-center gap-1.5 text-[11px] font-medium">
                    <span className="size-2 rounded-full" style={{ background: KIND_COLOR[k] }} aria-hidden /> {KIND_PLURAL[k]}
                  </div>
                  <ul className="space-y-0.5">
                    {list.map((i) => (
                      <li key={i.id}>
                        <button type="button" className="flex min-h-6 w-full items-center gap-1.5 rounded-md px-1.5 text-left hover:bg-accent" onClick={() => onSelect({ kind: "item", id: i.id, workflowId: wf.id })}>
                          <span className="min-w-0 flex-1 truncate">{i.name}</span>
                          {i.shared && <span className="text-[10px] text-muted-foreground">shared</span>}
                          {i.status !== "active" && <span className="text-[10px] text-muted-foreground">{i.status}</span>}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </>
        )}
        {wf && item && (
          <>
            <p className="text-muted-foreground">{item.description || "No description yet."}</p>
            <div className="flex flex-wrap items-center gap-1.5">
              <Status value={item.status} />
              {item.shared && <StatusChip tone="info">shared tool</StatusChip>}
            </div>
            <button type="button" className="min-h-7 w-full rounded-md px-1.5 text-left hover:bg-accent" onClick={() => onSelect({ kind: "workflow", id: wf.id })}>
              <span className="text-muted-foreground">In workflow </span><span className="font-medium">{wf.name}</span>
            </button>
          </>
        )}
      </div>
      {wf && (
        <footer className="border-t p-2.5">
          <Button asChild size="sm" className="w-full">
            <Link href={item ? `/studio?wf=${wf.id}&focus=${encodeURIComponent(item.id)}` : `/studio?wf=${wf.id}`}>
              Open in Workflow Studio <ArrowUpRight />
            </Link>
          </Button>
        </footer>
      )}
    </section>
  );
}
