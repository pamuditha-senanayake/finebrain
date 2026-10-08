"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useAgents, useClusters, useHumans, useTenant } from "@/lib/api/hooks";
import { initials, textOn } from "@/lib/format";
import { cn } from "@/lib/utils";
import { IdleDot, ThinkingOrb } from "./motion";

export function useLookup() {
  const agents = useAgents();
  const humans = useHumans();
  const clusters = useClusters();
  const tenant = useTenant();
  return useMemo(() => {
    const a = new Map((agents.data ?? []).map((x) => [x.id, x]));
    const h = new Map((humans.data ?? []).map((x) => [x.id, x]));
    const c = new Map((clusters.data ?? []).map((x) => [x.id, x]));
    return {
      agent: (id: string) => a.get(id),
      human: (id: string) => h.get(id),
      name: (id: string) => a.get(id)?.name ?? h.get(id)?.name ?? id,
      cluster: (id: string) => c.get(id)?.name ?? id,
      currency: tenant.data?.currency ?? "LKR",
      tz: tenant.data?.timezone,
    };
  }, [agents.data, humans.data, clusters.data, tenant.data]);
}

export function AgentChip({ id, link = true, className }: { id: string; link?: boolean; className?: string }) {
  const { agent } = useLookup();
  const a = agent(id);
  const body = (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5", className)}>
      {a?.status === "working" ? <ThinkingOrb kind={a.workKind} size={12} /> : <IdleDot tone={a?.status === "blocked" || a?.status === "error" ? "risk" : "neutral"} />}
      <span className="truncate">{a?.name ?? id}</span>
    </span>
  );
  return link && a ? (
    <Link href={`/l3/agents/${id}`} className="hover:underline" onClick={(e) => e.stopPropagation()}>
      {body}
    </Link>
  ) : (
    body
  );
}

export function PersonChip({ id, className }: { id: string; className?: string }) {
  const { human, agent } = useLookup();
  const h = human(id);
  if (!h) return <AgentChip id={id} className={className} />;
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5", className)} title={`${h.title} · ${h.tier}`}>
      <span className="grid size-5 shrink-0 place-items-center rounded-full text-[9px] font-semibold" style={{ background: h.color, color: textOn(h.color) }} aria-hidden>
        {initials(h.name)}
      </span>
      <span className="truncate">{h.name}</span>
      {agent(id) && null}
    </span>
  );
}
