"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { AccessDecision } from "@/contracts";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, type Column } from "@/components/brain/data-table";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentChip, useLookup } from "@/components/brain/names";
import { AccessCheckDialog } from "./access-check";
import { AgentsTab, PeopleTab, RulesTab, SourcesTab } from "./security-tabs";
import { CritBadge, Mono, PageHeader, QueryView, Section, Status } from "@/components/brain/primitives";
import { useAccessDecisions, useApprovals } from "@/lib/api/hooks";
import { dateTime } from "@/lib/format";

export function Security() {
  const [decision, setDecision] = useState<"all" | "deny" | "allow">("deny");
  const decisions = useAccessDecisions(decision === "all" ? {} : { decision });
  const [checking, setChecking] = useState<{ open: boolean; agentId?: string }>({ open: false });
  const approvals = useApprovals();
  const lookup = useLookup();
  const columns: Column<AccessDecision>[] = useMemo(
    () => [
      { id: "at", header: "When", width: "120px", value: (a) => a.at, cell: (a) => <span className="text-muted-foreground">{dateTime(a.at, lookup.tz)}</span> },
      { id: "decision", header: "Decision", width: "80px", value: (a) => a.decision, cell: (a) => <Status value={a.decision} /> },
      { id: "principal", header: "Principal", width: "minmax(130px,1fr)", value: (a) => lookup.name(a.principal), cell: (a) => <AgentChip id={a.principal} /> },
      { id: "obo", header: "For", width: "100px", value: (a) => (a.onBehalfOf ? lookup.name(a.onBehalfOf) : ""), hideOnMobile: true, cell: (a) => (a.onBehalfOf ? lookup.name(a.onBehalfOf) : <span className="text-muted-foreground">itself</span>) },
      { id: "resource", header: "Action and resource", width: "minmax(160px,1.2fr)", value: (a) => a.resource, cell: (a) => <Mono className="truncate">{a.resource}</Mono> },
      { id: "reason", header: "Why", width: "minmax(220px,2fr)", value: (a) => a.reason, hideOnMobile: true, cell: (a) => <div className="min-w-0"><div className="truncate" title={a.reason}>{a.reason}</div><Mono className="mt-0.5 block truncate text-[11px] text-muted-foreground">{a.ruleId}</Mono></div> },
      { id: "latency", header: "Latency", width: "70px", align: "right", value: (a) => a.latencyMs, hideOnMobile: true, cell: (a) => `${a.latencyMs} ms` },
    ],
    [lookup],
  );
  const pendingSecurity = (approvals.data ?? []).filter((a) => a.status === "pending" && a.criticality === 4);
  return (
    <div>
      <PageHeader
        title="Security"
        description="Who may do what, and every yes and no."
        actions={<Button onClick={() => setChecking({ open: true })}><ShieldCheck /> Check access</Button>}
      />
      {pendingSecurity.length > 0 && (
        <Section title="Waiting for you" className="mb-6">
          <ul className="space-y-3">
            {pendingSecurity.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-3 text-[15px]">
                <CritBadge level={a.criticality} />
                <Link href={`/l1/approvals/${a.id}`} className="font-medium hover:underline">{a.title}</Link>
                <span className="text-[14px] text-muted-foreground">{a.votes.filter((v) => v.decision === "approve").length} of {a.requiredApprovers.count} approved</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Tabs defaultValue="log">
        <TabsList>
          <TabsTrigger value="log">Decisions</TabsTrigger>
          <TabsTrigger value="agents">Agents</TabsTrigger>
          <TabsTrigger value="humans">People</TabsTrigger>
          <TabsTrigger value="rules">Rules</TabsTrigger>
          <TabsTrigger value="scopes">Data</TabsTrigger>
        </TabsList>
        <TabsContent value="log" className="mt-6">
          <QueryView query={decisions}>
            {(ds) => (
              <DataTable
                rowHeight={56}
                label="Invocation decision log"
                data={ds}
                columns={columns}
                getRowId={(a) => a.id}
                initialSort={{ id: "at", desc: true }}
                height="calc(100dvh - 380px)"
                emptyText={decision === "deny" ? "Nothing denied. Everything asked for was allowed." : "No decisions yet."}
                toolbar={
                  <ToggleGroup type="single" value={decision} onValueChange={(v) => v && setDecision(v as typeof decision)} variant="outline" size="sm" aria-label="Decision filter">
                    <ToggleGroupItem value="deny" className="px-3 text-[13px]">Denied</ToggleGroupItem>
                    <ToggleGroupItem value="allow" className="px-3 text-[13px]">Allowed</ToggleGroupItem>
                    <ToggleGroupItem value="all" className="px-3 text-[13px]">All</ToggleGroupItem>
                  </ToggleGroup>
                }
              />
            )}
          </QueryView>
        </TabsContent>
        <TabsContent value="agents" className="mt-6"><AgentsTab onCheck={(agentId) => setChecking({ open: true, agentId })} /></TabsContent>
        <TabsContent value="humans" className="mt-6"><PeopleTab /></TabsContent>
        <TabsContent value="rules" className="mt-6"><RulesTab /></TabsContent>
        <TabsContent value="scopes" className="mt-6"><SourcesTab /></TabsContent>
      </Tabs>
      <AccessCheckDialog key={checking.agentId ?? "any"} open={checking.open} agentId={checking.agentId} onOpenChange={(open) => setChecking((c) => ({ ...c, open }))} />
    </div>
  );
}
