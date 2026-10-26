"use client";

// hub.tsx: every connection, grouped by the platform it belongs to. A connection's feed is its sensor, so health and
// items in show on its row; the sources built into the brain sit under "Built in". Used by: connections page.
// Uses: add-dialog.tsx, details.tsx (SensorSheet), lib/api/connections.ts.
import { ChevronRight, Database, Globe, HelpCircle, Inbox, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { EmptyState, PageHeader, QueryView, Status, StatusChip } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import type { Sensor } from "@/contracts";
import { type Connection, byPlatform, useConnections } from "@/lib/api/connections";
import { useSensors } from "@/lib/api/hooks";
import { relTime } from "@/lib/format";
import { AddConnectionDialog, newConnectionHref } from "./add-dialog";
import { SensorSheet } from "./details";
import { RowMenu } from "./row-menu";

const KIND_ICON = { api: Globe, database: Database, other: HelpCircle } as const;
const TONE = { waiting: "neutral", delivered: "info", tested: "info", live: "ok", paused: "warn" } as const;
const BUILT_IN = "Built in";

/** One short line on where a connection stands, so nobody has to open it to know. */
function standing(c: Connection): string {
  if (c.status === "live") return c.kind === "database" ? `${c.tables.length} tables readable` : `${c.events} items in · last ${c.lastEventAt ? relTime(c.lastEventAt) : "none yet"}`;
  if (c.status === "waiting") return c.needs.length ? "Waiting for their answer" : "Being described";
  if (c.status === "delivered") return "Answer in · test next";
  return c.status === "tested" ? "Passed · ready to switch on" : "Off";
}

function ConnectionRow({ c }: { c: Connection }) {
  const Icon = KIND_ICON[c.kind];
  return (
    <li className="flex items-center pr-3 hover:bg-muted/50">
      <Link href={`/l2/connections?c=${c.id}`} className="flex min-w-0 flex-1 items-center gap-4 py-4 pl-5">
        <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-medium">{c.name}</span>
          <span className="block truncate text-[13px] text-muted-foreground">{standing(c)}</span>
        </span>
        <StatusChip tone={TONE[c.status]}>{c.status}</StatusChip>
        <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
      </Link>
      <RowMenu id={c.id} name={c.name} />
    </li>
  );
}

function PlatformCard({ platform, list, onAdd }: { platform: string; list: Connection[]; onAdd: () => void }) {
  const later = list.flatMap((c) => c.later.map((item) => ({ item, from: c.id })));
  return (
    <section className="overflow-hidden rounded-xl border bg-card" aria-label={platform}>
      <header className="flex items-center justify-between gap-3 px-5 pt-5 pb-3">
        <h2 className="truncate text-[15px] font-semibold">{platform}</h2>
        <Button variant="ghost" size="sm" onClick={onAdd}><Plus /> Add</Button>
      </header>
      <ul className="divide-y border-t">{list.map((c) => <ConnectionRow key={c.id} c={c} />)}</ul>
      {later.map(({ item, from }) => (
        <div key={item} className="flex items-center gap-4 border-t bg-muted/30 px-5 py-3.5">
          <span className="min-w-0 flex-1 truncate text-[13px] text-muted-foreground">Next up: {item}</span>
          <Button size="sm" variant="outline" asChild><Link href={newConnectionHref("other", platform, item, from)}>Start</Link></Button>
        </div>
      ))}
    </section>
  );
}

function BuiltIn({ sensors, onOpen }: { sensors: Sensor[]; onOpen: (id: string) => void }) {
  return (
    <section className="overflow-hidden rounded-xl border bg-card" aria-label={BUILT_IN}>
      <h2 className="px-5 pt-5 pb-3 text-[15px] font-semibold">{BUILT_IN}</h2>
      <ul className="divide-y border-t">
        {sensors.map((s) => (
          <li key={s.id}>
            <button type="button" onClick={() => onOpen(s.id)} className="flex w-full items-center gap-4 px-5 py-4 text-left hover:bg-muted/50">
              <Inbox className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-medium">{s.name}</span>
                <span className="block truncate text-[13px] text-muted-foreground">last item {relTime(s.lastEventAt)}</span>
              </span>
              <Status value={s.health} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ConnectionsHub() {
  const connections = useConnections();
  const sensors = useSensors();
  const [adding, setAdding] = useState<{ platform?: string } | null>(null);
  const [sensorId, setSensorId] = useState<string | null>(null);
  const groups = byPlatform(connections.data ?? []);
  return (
    <div className="space-y-8">
      <PageHeader title="Connections" description="Every outside system the brain works with." actions={<Button onClick={() => setAdding({})}><Plus /> Add connection</Button>} />
      <QueryView query={connections} isEmpty={() => false}>
        {() => (
          <div className="mx-auto max-w-3xl space-y-6">
            {groups.length === 0 && <EmptyState title="Nothing connected yet" description="Add a connection. The guide walks you through it." />}
            {groups.map(([platform, list]) => <PlatformCard key={platform} platform={platform} list={list} onAdd={() => setAdding({ platform })} />)}
            {sensors.data && sensors.data.length > 0 && <BuiltIn sensors={sensors.data} onOpen={setSensorId} />}
          </div>
        )}
      </QueryView>
      <AddConnectionDialog key={adding?.platform ?? ""} open={adding !== null} onOpenChange={(open) => !open && setAdding(null)} platforms={groups.map(([p]) => p)} platform={adding?.platform} />
      <SensorSheet sensor={sensors.data?.find((s) => s.id === sensorId) ?? null} onClose={() => setSensorId(null)} />
    </div>
  );
}
