"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import type { AuditEvent } from "@/contracts";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DataTable, type Column } from "@/components/brain/data-table";
import { useLookup } from "@/components/brain/names";
import { CritBadge, EnvBadge, Mono, PageHeader, QueryView, StatusChip } from "@/components/brain/primitives";
import { useAudit } from "@/lib/api/hooks";
import { dateTime } from "@/lib/format";

export function AuditTrail() {
  const params = useSearchParams();
  const router = useRouter();
  const correlation = params.get("correlation") ?? "";
  const actor = params.get("actor") ?? "";
  const env = params.get("env") ?? "";
  const minCriticality = Number(params.get("min") ?? 0);
  const audit = useAudit({ correlation: correlation || undefined, actor: actor || undefined, env: env || undefined, minCriticality });
  const lookup = useLookup();
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v && v !== "any") next.set(k, v);
    else next.delete(k);
    router.replace(`/l1/audit?${next.toString()}`);
  };
  const columns: Column<AuditEvent>[] = useMemo(
    () => [
      { id: "at", header: "When", width: "130px", value: (e) => e.at, cell: (e) => <span className="text-muted-foreground">{dateTime(e.at, lookup.tz)}</span> },
      { id: "actor", header: "Actor", width: "minmax(140px,1fr)", value: (e) => e.actor.name, cell: (e) => <span className="flex items-center gap-1.5"><StatusChip tone={e.actor.kind === "agent" ? "agent" : e.actor.kind === "human" ? "info" : "neutral"}>{e.actor.kind}</StatusChip><span className="truncate">{e.actor.name}</span></span> },
      { id: "action", header: "Action", width: "minmax(150px,1fr)", value: (e) => e.action, cell: (e) => <Mono>{e.action}</Mono> },
      { id: "target", header: "Object", width: "minmax(160px,1.2fr)", value: (e) => e.target.label, hideOnMobile: true, cell: (e) => <span className="truncate" title={e.target.id}>{e.target.label}</span> },
      { id: "detail", header: "Detail", width: "minmax(200px,2fr)", value: (e) => e.detail, hideOnMobile: true, cell: (e) => <span className="truncate text-muted-foreground" title={e.detail}>{e.detail}</span> },
      { id: "env", header: "Env", width: "90px", value: (e) => e.env, hideOnMobile: true, cell: (e) => <EnvBadge env={e.env} /> },
      { id: "crit", header: "Level", width: "56px", value: (e) => e.criticality, cell: (e) => <CritBadge level={e.criticality} /> },
    ],
    [lookup.tz],
  );
  return (
    <div>
      <PageHeader title="Audit trail" description="Read only. Every consequential event by any human or agent, filterable by actor, object, environment and criticality." />
      <QueryView query={audit}>
        {(rows) => (
          <DataTable
            label="Audit events"
            data={rows}
            columns={columns}
            getRowId={(e) => e.id}
            initialSort={{ id: "at", desc: true }}
            height="calc(100dvh - 250px)"
            searchPlaceholder="Filter by object, action or detail"
            toolbar={
              <div className="flex flex-wrap gap-2">
                {correlation && (
                  <button type="button" onClick={() => set("correlation", "")} className="rounded-full border px-2 py-0.5 text-xs">
                    correlation <Mono>{correlation}</Mono> ✕
                  </button>
                )}
                <Select value={actor || "any"} onValueChange={(v) => set("actor", v)}>
                  <SelectTrigger size="sm" className="h-8 w-[120px] text-xs" aria-label="Actor">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any actor</SelectItem>
                    <SelectItem value="human">Humans</SelectItem>
                    <SelectItem value="agent">Agents</SelectItem>
                    <SelectItem value="system">System</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={env || "any"} onValueChange={(v) => set("env", v)}>
                  <SelectTrigger size="sm" className="h-8 w-[130px] text-xs" aria-label="Environment">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any env</SelectItem>
                    <SelectItem value="production">Production</SelectItem>
                    <SelectItem value="staging">Staging</SelectItem>
                    <SelectItem value="sandbox">Sandbox</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={String(minCriticality)} onValueChange={(v) => set("min", v === "0" ? "" : v)}>
                  <SelectTrigger size="sm" className="h-8 w-[110px] text-xs" aria-label="Minimum criticality">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[0, 1, 2, 3, 4].map((c) => (
                      <SelectItem key={c} value={String(c)}>
                        {c === 0 ? "Any level" : `C${c} and up`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            }
          />
        )}
      </QueryView>
    </div>
  );
}
