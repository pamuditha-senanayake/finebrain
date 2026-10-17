"use client";

import { Check, ChevronRight, Loader2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Switch } from "@/components/ui/switch";
import { connectorById } from "@/lib/connect/catalog";
import { STAGE_LABEL, itemsOf, stageOf, useConnect, useStageClock, type Connection } from "@/lib/connect/store";
import { cn } from "@/lib/utils";
import { ConnectorMark } from "./connect-form";
import { otherTool } from "./connector-picker";
import { ConnectionSheet } from "./details";

/**
 * The systems the brain is linked to. Each row has an on/off switch and opens its details on click.
 * Only a connection that is changing now carries the accent colour.
 * `empty` shows when there are none; without it the list hides itself.
 */
export function ConnectorsList({ className, title = "Connectors", empty }: { className?: string; title?: string; empty?: ReactNode }) {
  const connections = useConnect((s) => s.connections);
  const setEnabled = useConnect((s) => s.setEnabled);
  const now = useStageClock(connections);
  const [openId, setOpenId] = useState<string | null>(null);
  if (!connections.length && !empty) return null;
  const on = connections.filter((c) => c.enabled !== false).length;
  return (
    <section className={cn("rounded-2xl border bg-card p-5 sm:p-6", className)} aria-label={title}>
      <div className="mb-2 flex items-baseline justify-between gap-4">
        <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>
        {connections.length > 0 && <span className="text-sm text-muted-foreground tabular-nums">{on} on</span>}
      </div>
      {connections.length ? (
        <ul className="divide-y">
          {[...connections].reverse().map((c) => (
            <Row key={c.id} c={c} now={now} onOpen={() => setOpenId(c.id)} onToggle={(v) => setEnabled(c.id, v)} />
          ))}
        </ul>
      ) : empty}
      <ConnectionSheet connection={connections.find((c) => c.id === openId) ?? null} now={now} onClose={() => setOpenId(null)} />
    </section>
  );
}

function Row({ c, now, onOpen, onToggle }: { c: Connection; now: number; onOpen: () => void; onToggle: (on: boolean) => void }) {
  const stage = stageOf(c, now);
  const live = stage === "connecting" || stage === "reading";
  return (
    <li className="flex items-center gap-3">
      <button type="button" onClick={onOpen} className="-mx-2 flex min-w-0 flex-1 items-center gap-4 rounded-xl px-2 py-3 text-left transition-colors hover:bg-table-hover focus-visible:bg-table-hover focus-visible:outline-none">
        <ConnectorMark connector={connectorById(c.connectorId) ?? otherTool(c.name)} className={cn("size-9", stage === "paused" && "opacity-50")} />
        <div className="min-w-0 flex-1">
          <div className={cn("truncate text-[15px] font-medium", stage === "paused" && "text-muted-foreground")}>{c.name}</div>
          <div className="truncate text-[13px] text-muted-foreground">{c.detail}</div>
        </div>
        <span className={cn("hidden shrink-0 items-center gap-1.5 text-sm sm:inline-flex", live ? "text-primary" : "text-muted-foreground")}>
          {live ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : stage === "known" ? <Check className="size-3.5 text-ok" aria-hidden /> : null}
          {stage === "known" ? `${itemsOf(c).toLocaleString()} items` : STAGE_LABEL[stage]}
        </span>
        <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </button>
      {c.method !== "request" && <Switch checked={c.enabled !== false} onCheckedChange={onToggle} aria-label={`${c.name} ${c.enabled !== false ? "on" : "off"}`} />}
    </li>
  );
}
