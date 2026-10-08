"use client";

import Link from "next/link";
import { useMemo } from "react";
import type { ResolverRule } from "@/contracts";
import { DataTable, type Column } from "@/components/brain/data-table";
import { AgentChip, useLookup } from "@/components/brain/names";
import { Mono, PageHeader, QueryView } from "@/components/brain/primitives";
import { useResolver } from "@/lib/api/hooks";
import { pct, relTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export function Resolver() {
  const rules = useResolver();
  const lookup = useLookup();
  const columns: Column<ResolverRule>[] = useMemo(
    () => [
      { id: "priority", header: "#", width: "44px", align: "right", value: (r) => r.priority, cell: (r) => <span className="text-muted-foreground">{r.priority}</span> },
      { id: "event", header: "When this happens", width: "minmax(220px,2fr)", value: (r) => r.event, cell: (r) => <span className="truncate" title={r.event}>{r.event}</span> },
      { id: "match", header: "Matches", width: "minmax(140px,1fr)", value: (r) => r.match, hideOnMobile: true, cell: (r) => <Mono className="truncate">{r.match}</Mono> },
      { id: "skill", header: "Skill", width: "minmax(160px,1.2fr)", value: (r) => r.skill.id, cell: (r) => <Link href={`/l2/skills/${r.skill.id}`} className="truncate hover:underline" onClick={(e) => e.stopPropagation()}><Mono>{r.skill.id} v{r.skill.version}</Mono></Link> },
      { id: "agent", header: "Agent", width: "minmax(130px,1fr)", value: (r) => lookup.name(r.agentId), hideOnMobile: true, cell: (r) => <AgentChip id={r.agentId} /> },
      { id: "eval", header: "Trigger evals", width: "120px", align: "right", value: (r) => r.triggerEval.passRate, cell: (r) => <span className={cn("tabular", r.triggerEval.passRate < 0.9 && "text-warn-fg")}>{pct(r.triggerEval.passRate)} of {r.triggerEval.cases}</span> },
      { id: "ran", header: "Last run", width: "100px", value: (r) => r.triggerEval.lastRunAt, hideOnMobile: true, cell: (r) => <span className="text-muted-foreground">{relTime(r.triggerEval.lastRunAt)}</span> },
    ],
    [lookup],
  );
  return (
    <div>
      <PageHeader title="Resolver" description="The org chart for tasks: it routes each incoming event to an agent and a skill. Trigger evals prove the right skill fires." />
      <QueryView query={rules}>{(rs) => <DataTable label="Resolver rules" data={rs} columns={columns} getRowId={(r) => r.id} initialSort={{ id: "priority", desc: false }} height="calc(100dvh - 240px)" />}</QueryView>
    </div>
  );
}
