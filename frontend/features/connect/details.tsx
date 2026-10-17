"use client";

import { ArrowRight, Radar } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import type { Sensor } from "@/contracts";
import { useLookup } from "@/components/brain/names";
import { Status } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { METHOD, connectorById, listenOf } from "@/lib/connect/catalog";
import { STAGE_LABEL, itemsOf, lastSyncOf, stageOf, useConnect, type Connection } from "@/lib/connect/store";
import { dateTime, relTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useWorkflowIndex } from "@/lib/workflow-index";
import { ConnectorMark } from "./connect-form";
import { otherTool } from "./connector-picker";

/** One side panel for a connector or a sensor: the name, an on/off switch, then plain rows of detail. */
function Panel({ open, onClose, mark, title, sub, on, onToggle, rows, footer }: { open: boolean; onClose: () => void; mark: ReactNode; title: string; sub: string; on: boolean; onToggle?: (on: boolean) => void; rows: [string, ReactNode][]; footer?: ReactNode }) {
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-md">
        <div className="flex items-center gap-4 border-b px-6 pb-6 pt-8">
          {mark}
          <div className="min-w-0 flex-1">
            <SheetTitle className="truncate text-lg font-semibold">{title}</SheetTitle>
            <SheetDescription className="mt-0.5 truncate text-sm">{sub}</SheetDescription>
          </div>
        </div>
        {onToggle && (
          <label className="flex cursor-pointer items-center justify-between gap-4 border-b px-6 py-5">
            <div>
              <div className="text-[15px] font-medium">{on ? "Listening" : "Off"}</div>
              <div className="text-[13px] text-muted-foreground">{on ? "New data flows into knowledge." : "Paused. Nothing new is read."}</div>
            </div>
            <Switch checked={on} onCheckedChange={onToggle} aria-label={on ? "Turn off" : "Turn on"} />
          </label>
        )}
        <dl className="flex-1 space-y-5 overflow-y-auto px-6 py-6">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt className="text-xs font-medium uppercase tracking-[0.07em] text-muted-foreground">{k}</dt>
              <dd className="mt-1.5 text-[15px] leading-relaxed">{v}</dd>
            </div>
          ))}
        </dl>
        {footer && <div className="flex flex-wrap gap-2 border-t px-6 py-5">{footer}</div>}
      </SheetContent>
    </Sheet>
  );
}

const List = ({ items, mono }: { items: string[]; mono?: boolean }) =>
  items.length ? (
    <ul className="space-y-1">
      {items.map((x) => <li key={x} className={cn("break-all", mono && "font-mono text-[13px]")}>{x}</li>)}
    </ul>
  ) : <span className="text-muted-foreground">None</span>;

/** Everything about one connector: what it listens to, how, what it reads, since when, and how much it has learned. */
export function ConnectionSheet({ connection: c, now, onClose }: { connection: Connection | null; now: number; onClose: () => void }) {
  const setEnabled = useConnect((s) => s.setEnabled);
  const disconnect = useConnect((s) => s.disconnect);
  const [sure, setSure] = useState(false);
  if (!c) return <Panel open={false} onClose={onClose} mark={null} title="" sub="" on={false} rows={[]} />;
  const connector = connectorById(c.connectorId) ?? otherTool(c.name);
  const stage = stageOf(c, now);
  const sync = lastSyncOf(c, now);
  const requested = c.method === "request";
  const rows: [string, ReactNode][] = [
    ["Listening to", <List key="l" items={c.detail.split(",").map((x) => x.trim()).filter(Boolean)} mono={c.method !== "oauth"} />],
    ["Status", stage === "known" ? `In knowledge · ${itemsOf(c).toLocaleString()} items` : STAGE_LABEL[stage]],
    ["Connected", dateTime(new Date(c.addedAt).toISOString())],
    ...(requested ? [] : ([
      ["Last sync", sync && c.enabled !== false ? relTime(new Date(sync).toISOString(), now) : "Not yet"],
      ["How", `${METHOD[c.method as keyof typeof METHOD].label} · read only`],
      ["Reads", <List key="r" items={listenOf(connector).reads} />],
    ] as [string, ReactNode][])),
  ];
  return (
    <Panel
      open
      onClose={() => { setSure(false); onClose(); }}
      mark={<ConnectorMark connector={connector} />}
      title={c.name}
      sub={requested ? "Connector requested" : METHOD[c.method as keyof typeof METHOD].label}
      on={c.enabled !== false}
      onToggle={requested ? undefined : (on) => setEnabled(c.id, on)}
      rows={rows}
      footer={
        <>
          {stage === "known" && <Button asChild variant="outline"><Link href="/l2/graph">Open knowledge <ArrowRight /></Link></Button>}
          <Button variant={sure ? "destructive" : "ghost"} className={cn("ml-auto", !sure && "text-muted-foreground")} onClick={() => { if (!sure) return setSure(true); disconnect(c.id); setSure(false); onClose(); }}>
            {sure ? "Yes, disconnect" : "Disconnect"}
          </Button>
        </>
      }
    />
  );
}

/** Everything about one sensor from the backend: its source, events, who listens, access, retention and personal data. */
export function SensorSheet({ sensor: s, onClose }: { sensor: Sensor | null; onClose: () => void }) {
  const off = useConnect((st) => (s ? !!st.sensorsOff[s.id] : false));
  const setSensorOn = useConnect((st) => st.setSensorOn);
  const lookup = useLookup();
  const index = useWorkflowIndex();
  if (!s) return <Panel open={false} onClose={onClose} mark={null} title="" sub="" on={false} rows={[]} />;
  const rows: [string, ReactNode][] = [
    ["Listening to", <span key="s" className="break-all">{s.source}</span>],
    ["Health", <Status key="h" value={off ? "paused" : s.health} />],
    ["Events", <List key="e" items={s.events} mono />],
    ["Last event", `${relTime(s.lastEventAt)} · ${s.eventsPerHour.toLocaleString()} an hour`],
    ["Used by", <List key="u" items={s.subscribers.map((x) => lookup.name(x))} />],
    ["Workflows", <List key="w" items={index.of("sensor", s.id)} />],
    ["Access", <List key="a" items={s.scopes} mono />],
    ["Personal data", s.personalData ? "Yes, masked before use" : "No"],
    ["Kept for", `${s.retentionDays} days`],
    ["Cluster", lookup.cluster(s.clusterId)],
  ];
  return (
    <Panel
      open
      onClose={onClose}
      mark={<span className="grid size-10 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground" aria-hidden><Radar className="size-[18px]" /></span>}
      title={s.name}
      sub={s.kind[0].toUpperCase() + s.kind.slice(1)}
      on={!off}
      onToggle={(on) => setSensorOn(s.id, on)}
      rows={rows}
    />
  );
}
