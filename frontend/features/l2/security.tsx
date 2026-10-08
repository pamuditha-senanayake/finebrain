"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { AccessDecision } from "@/contracts";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, type Column } from "@/components/brain/data-table";
import { AgentChip, PersonChip, useLookup } from "@/components/brain/names";
import { CritBadge, Mono, PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useAccessDecisions, useAccessRules, useAgents, useApprovals, useGrants, useHumans } from "@/lib/api/hooks";
import { dateTime } from "@/lib/format";

export function Security() {
  const [decision, setDecision] = useState<"all" | "deny" | "allow">("deny");
  const decisions = useAccessDecisions(decision === "all" ? {} : { decision });
  const rules = useAccessRules();
  const agents = useAgents();
  const humans = useHumans();
  const grants = useGrants();
  const approvals = useApprovals();
  const lookup = useLookup();
  const columns: Column<AccessDecision>[] = useMemo(
    () => [
      { id: "at", header: "When", width: "120px", value: (a) => a.at, cell: (a) => <span className="text-muted-foreground">{dateTime(a.at, lookup.tz)}</span> },
      { id: "decision", header: "Decision", width: "80px", value: (a) => a.decision, cell: (a) => <Status value={a.decision} /> },
      { id: "principal", header: "Principal", width: "minmax(130px,1fr)", value: (a) => lookup.name(a.principal), cell: (a) => <AgentChip id={a.principal} /> },
      { id: "obo", header: "On behalf of", width: "120px", value: (a) => (a.onBehalfOf ? lookup.name(a.onBehalfOf) : ""), hideOnMobile: true, cell: (a) => (a.onBehalfOf ? lookup.name(a.onBehalfOf) : <span className="text-muted-foreground">itself</span>) },
      { id: "resource", header: "Action and resource", width: "minmax(160px,1.2fr)", value: (a) => a.resource, cell: (a) => <Mono className="truncate">{a.resource}</Mono> },
      { id: "rule", header: "Deciding rule", width: "minmax(120px,1fr)", value: (a) => a.ruleId, hideOnMobile: true, cell: (a) => <Mono className="truncate">{a.ruleId}</Mono> },
      { id: "reason", header: "Reason", width: "minmax(180px,1.6fr)", value: (a) => a.reason, hideOnMobile: true, cell: (a) => <span className="truncate text-muted-foreground" title={a.reason}>{a.reason}</span> },
      { id: "latency", header: "Latency", width: "70px", align: "right", value: (a) => a.latencyMs, hideOnMobile: true, cell: (a) => `${a.latencyMs} ms` },
    ],
    [lookup],
  );
  const pendingSecurity = (approvals.data ?? []).filter((a) => a.status === "pending" && a.criticality === 4);
  return (
    <div>
      <PageHeader title="Security and access" description="Human roles and attributes, agent capability grants, connector scopes, and every allow and deny with the principal, on whose behalf, the deciding rule and the latency." />
      {pendingSecurity.length > 0 && (
        <Section title="Proposed by the Security Sentinel" className="mb-4">
          <ul className="space-y-2">
            {pendingSecurity.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-2 text-sm">
                <CritBadge level={a.criticality} />
                <Link href={`/l1/approvals/${a.id}`} className="font-medium hover:underline">{a.title}</Link>
                <span className="text-xs text-muted-foreground">needs {a.requiredApprovers.count} {a.requiredApprovers.tier} approvers · {a.votes.filter((v) => v.decision === "approve").length} so far</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Tabs defaultValue="log">
        <TabsList>
          <TabsTrigger value="log">Decision log</TabsTrigger>
          <TabsTrigger value="agents">Agent capabilities</TabsTrigger>
          <TabsTrigger value="humans">Human roles</TabsTrigger>
          <TabsTrigger value="rules">Access rules</TabsTrigger>
          <TabsTrigger value="scopes">Connector scopes</TabsTrigger>
        </TabsList>
        <TabsContent value="log" className="mt-3">
          <QueryView query={decisions}>
            {(ds) => (
              <DataTable
                label="Invocation decision log"
                data={ds}
                columns={columns}
                getRowId={(a) => a.id}
                initialSort={{ id: "at", desc: true }}
                height="calc(100dvh - 330px)"
                toolbar={
                  <ToggleGroup type="single" value={decision} onValueChange={(v) => v && setDecision(v as typeof decision)} variant="outline" size="sm" aria-label="Decision filter">
                    <ToggleGroupItem value="deny" className="px-2.5 text-xs">Denied</ToggleGroupItem>
                    <ToggleGroupItem value="allow" className="px-2.5 text-xs">Allowed</ToggleGroupItem>
                    <ToggleGroupItem value="all" className="px-2.5 text-xs">All</ToggleGroupItem>
                  </ToggleGroup>
                }
              />
            )}
          </QueryView>
        </TabsContent>
        <TabsContent value="agents" className="mt-3">
          <QueryView query={agents}>
            {(as) => (
              <ul className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {as.slice(0, 120).map((a) => (
                  <li key={a.id} className="rounded-lg border bg-card p-3 text-sm">
                    <div className="flex items-center justify-between"><AgentChip id={a.id} /><StatusChip tone={a.accessLevel === "restricted" ? "risk" : a.accessLevel === "confidential" ? "warn" : "neutral"}>{a.accessLevel}</StatusChip></div>
                    <ul className="mt-2 flex flex-wrap gap-1">
                      {a.capabilities.map((c) => <li key={c}><Mono className="rounded bg-muted px-1">{c}</Mono></li>)}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </TabsContent>
        <TabsContent value="humans" className="mt-3">
          <QueryView query={humans}>
            {(hs) => (
              <table className="w-full text-sm">
                <thead className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                  <tr><th className="py-1.5 font-medium">Person</th><th className="py-1.5 font-medium">Tier</th><th className="py-1.5 font-medium">Roles</th><th className="py-1.5 font-medium">Attributes</th><th className="py-1.5 font-medium">Approves up to</th></tr>
                </thead>
                <tbody>
                  {hs.map((h) => (
                    <tr key={h.id} className="border-t">
                      <td className="py-2"><PersonChip id={h.id} /></td>
                      <td className="py-2">{h.tier}</td>
                      <td className="py-2 text-xs">{h.roles.join(", ")}</td>
                      <td className="py-2"><Mono className="text-xs">{Object.entries(h.attributes).map(([k, v]) => `${k}=${v}`).join(", ")}</Mono></td>
                      <td className="py-2">{h.maxApprovalCriticality > 0 ? <CritBadge level={h.maxApprovalCriticality} /> : <span className="text-xs text-muted-foreground">cannot approve</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </QueryView>
        </TabsContent>
        <TabsContent value="rules" className="mt-3">
          <QueryView query={rules}>
            {(rs) => (
              <ul className="grid gap-2 md:grid-cols-2">
                {rs.map((r) => (
                  <li key={r.id} className="rounded-lg border bg-card p-3 text-sm">
                    <div className="flex items-center justify-between gap-2"><span className="font-medium">{r.name}</span><StatusChip tone={r.sensitivity === "restricted" ? "risk" : "neutral"}>{r.sensitivity}</StatusChip></div>
                    <p className="mt-1 text-xs text-muted-foreground">{r.description}</p>
                    <p className="mt-1 text-xs">Applies to <Mono>{r.appliesTo}</Mono>{r.requiresCapability && <> · needs <Mono>{r.requiresCapability}</Mono></>}{r.requiresRoles.length > 0 && <> · roles {r.requiresRoles.join(", ")}</>}</p>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </TabsContent>
        <TabsContent value="scopes" className="mt-3">
          <QueryView query={grants}>
            {(gs) => (
              <ul className="space-y-2">
                {gs.map((g) => (
                  <li key={g.id} className="flex flex-wrap items-center gap-3 rounded-lg border bg-card p-3 text-sm">
                    <div className="min-w-0 flex-1">
                      <div className="font-medium">{g.source}</div>
                      <div className="text-xs text-muted-foreground">{g.scope} · retention {g.retentionDays} days · {g.agents.map((a) => lookup.name(a)).join(", ")}</div>
                    </div>
                    <Status value={g.status} />
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </TabsContent>
      </Tabs>
    </div>
  );
}
