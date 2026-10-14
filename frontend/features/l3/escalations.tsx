"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { Run } from "@/contracts";
import { DataTable, type Column } from "@/components/brain/data-table";
import { AgentChip, useLookup } from "@/components/brain/names";
import { CritBadge, EmptyState, PageHeader, QueryView, Status, StatusChip } from "@/components/brain/primitives";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useAgents, useEscalations } from "@/lib/api/hooks";
import { relTime } from "@/lib/format";

type Bucket = "all" | "escalated" | "pending";
/** Escalated: a person has picked it up. To be escalated: flagged by the agent, waiting for a supervisor agent or a person to triage it. */
const isEscalated = (r: Run) => !!r.escalation?.assignee;

const RISK = { high: 3, medium: 2, low: 1 } as const;

export function Escalations() {
  const escalations = useEscalations();
  const router = useRouter();
  const lookup = useLookup();
  const agents = useAgents();
  const [bucket, setBucket] = useState<Bucket>("all");
  const supervisor = agents.data?.find((a) => a.kind === "supervisor")?.name ?? "Supervisor agent";
  const columns: Column<Run>[] = useMemo(
    () => [
      { id: "risk", header: "Risk", width: "80px", value: (r) => (r.escalation ? RISK[r.escalation.risk] * 10 + r.escalation.criticality : 0), cell: (r) => <StatusChip tone={r.escalation?.risk === "high" ? "risk" : r.escalation?.risk === "medium" ? "warn" : "neutral"}>{r.escalation?.risk}</StatusChip> },
      { id: "crit", header: "Level", width: "56px", value: (r) => r.escalation?.criticality ?? 0, cell: (r) => <CritBadge level={r.escalation?.criticality ?? 0} /> },
      { id: "subject", header: "Case", width: "minmax(180px,1.3fr)", value: (r) => r.subject, cell: (r) => <span className="truncate font-medium">{r.subject}</span> },
      { id: "reason", header: "Why the agent stopped", width: "minmax(220px,2fr)", value: (r) => r.escalation?.reason ?? "", hideOnMobile: true, cell: (r) => <span className="truncate text-muted-foreground" title={r.escalation?.reason}>{r.escalation?.reason}</span> },
      { id: "agent", header: "Agent", width: "minmax(120px,0.8fr)", value: (r) => lookup.name(r.agentId), hideOnMobile: true, cell: (r) => <AgentChip id={r.agentId} /> },
      { id: "waiting", header: "Waiting", width: "100px", value: (r) => -Date.parse(r.escalation?.since ?? r.startedAt), cell: (r) => <span className="text-muted-foreground">{relTime(r.escalation?.since ?? r.startedAt)}</span> },
      { id: "status", header: "Status", width: "96px", value: (r) => r.status, hideOnMobile: true, cell: (r) => <Status value={r.status} /> },
      { id: "category", header: "Category", width: "130px", value: (r) => (isEscalated(r) ? 1 : 0), cell: (r) => <StatusChip tone={isEscalated(r) ? "risk" : "warn"}>{isEscalated(r) ? "Escalated" : "To be escalated"}</StatusChip> },
      { id: "assignee", header: "Triaged by", width: "120px", value: (r) => (r.escalation?.assignee ? lookup.name(r.escalation.assignee) : ""), hideOnMobile: true, cell: (r) => (r.escalation?.assignee ? lookup.name(r.escalation.assignee) : <span className="text-muted-foreground">{supervisor} (pending)</span>) },
    ],
    [lookup, supervisor],
  );
  return (
    <div>
      <PageHeader title="Escalations" description="Sorted by risk and waiting time. Escalated cases have a person on them; cases to be escalated are waiting for a supervisor agent or a person to triage." />
      <QueryView query={escalations} empty={<EmptyState title="No open escalations" description="Agents are handling everything inside policy." />}>
        {(all) => {
          const rows = bucket === "all" ? all : all.filter((r) => (bucket === "escalated") === isEscalated(r));
          const n = { escalated: all.filter(isEscalated).length, pending: all.filter((r) => !isEscalated(r)).length };
          return (
          <div className="space-y-3">
          <ToggleGroup type="single" value={bucket} onValueChange={(v) => v && setBucket(v as Bucket)} variant="outline" size="sm" aria-label="Category">
            <ToggleGroupItem value="all" className="px-3 text-xs">All {all.length}</ToggleGroupItem>
            <ToggleGroupItem value="escalated" className="px-3 text-xs">Escalated {n.escalated}</ToggleGroupItem>
            <ToggleGroupItem value="pending" className="px-3 text-xs">To be escalated {n.pending}</ToggleGroupItem>
          </ToggleGroup>
          <DataTable
            label="Escalations"
            data={rows}
            columns={columns}
            getRowId={(r) => r.id}
            initialSort={{ id: "risk", desc: true }}
            onRowClick={(r) => router.push(r.conversationId ? `/l3/conversations/${r.conversationId}` : `/l3/runs/${r.id}`)}
            height="calc(100dvh - 290px)"
          />
          </div>
          );
        }}
      </QueryView>
    </div>
  );
}
