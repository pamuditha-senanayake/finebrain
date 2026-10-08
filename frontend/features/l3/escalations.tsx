"use client";

import { useRouter } from "next/navigation";
import { useMemo } from "react";
import type { Run } from "@/contracts";
import { DataTable, type Column } from "@/components/brain/data-table";
import { AgentChip, useLookup } from "@/components/brain/names";
import { CritBadge, EmptyState, PageHeader, QueryView, Status, StatusChip } from "@/components/brain/primitives";
import { useEscalations } from "@/lib/api/hooks";
import { relTime } from "@/lib/format";

const RISK = { high: 3, medium: 2, low: 1 } as const;

export function Escalations() {
  const escalations = useEscalations();
  const router = useRouter();
  const lookup = useLookup();
  const columns: Column<Run>[] = useMemo(
    () => [
      { id: "risk", header: "Risk", width: "80px", value: (r) => (r.escalation ? RISK[r.escalation.risk] * 10 + r.escalation.criticality : 0), cell: (r) => <StatusChip tone={r.escalation?.risk === "high" ? "risk" : r.escalation?.risk === "medium" ? "warn" : "neutral"}>{r.escalation?.risk}</StatusChip> },
      { id: "crit", header: "Level", width: "56px", value: (r) => r.escalation?.criticality ?? 0, cell: (r) => <CritBadge level={r.escalation?.criticality ?? 0} /> },
      { id: "subject", header: "Case", width: "minmax(180px,1.3fr)", value: (r) => r.subject, cell: (r) => <span className="truncate font-medium">{r.subject}</span> },
      { id: "reason", header: "Why the agent stopped", width: "minmax(220px,2fr)", value: (r) => r.escalation?.reason ?? "", hideOnMobile: true, cell: (r) => <span className="truncate text-muted-foreground" title={r.escalation?.reason}>{r.escalation?.reason}</span> },
      { id: "agent", header: "Agent", width: "minmax(120px,0.8fr)", value: (r) => lookup.name(r.agentId), hideOnMobile: true, cell: (r) => <AgentChip id={r.agentId} /> },
      { id: "waiting", header: "Waiting", width: "100px", value: (r) => -Date.parse(r.escalation?.since ?? r.startedAt), cell: (r) => <span className="text-muted-foreground">{relTime(r.escalation?.since ?? r.startedAt)}</span> },
      { id: "status", header: "Status", width: "96px", value: (r) => r.status, hideOnMobile: true, cell: (r) => <Status value={r.status} /> },
      { id: "assignee", header: "Assignee", width: "120px", value: (r) => (r.escalation?.assignee ? lookup.name(r.escalation.assignee) : ""), hideOnMobile: true, cell: (r) => (r.escalation?.assignee ? lookup.name(r.escalation.assignee) : <span className="text-muted-foreground">unassigned</span>) },
    ],
    [lookup],
  );
  return (
    <div>
      <PageHeader title="Escalations" description="Sorted by risk and waiting time, with the reason each agent stopped." />
      <QueryView query={escalations} empty={<EmptyState title="No open escalations" description="Agents are handling everything inside policy." />}>
        {(rows) => (
          <DataTable
            label="Escalations"
            data={rows}
            columns={columns}
            getRowId={(r) => r.id}
            initialSort={{ id: "risk", desc: true }}
            onRowClick={(r) => router.push(r.conversationId ? `/l3/conversations/${r.conversationId}` : `/l3/runs/${r.id}`)}
            height="calc(100dvh - 240px)"
          />
        )}
      </QueryView>
    </div>
  );
}
