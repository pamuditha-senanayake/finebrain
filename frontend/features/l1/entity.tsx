"use client";

import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { Progress } from "@/components/ui/progress";
import { PersonChip, useLookup } from "@/components/brain/names";
import { SimpleTable } from "@/components/brain/simple-table";
import { PageHeader, QueryView, SampleBadge, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useNow, useObligations, useRisks } from "@/lib/api/hooks";
import { date } from "@/lib/format";
import { daysUntil } from "@/lib/governance/readiness";
import { cn } from "@/lib/utils";

export function EntityProtection() {
  const obligations = useObligations();
  const risks = useRisks();
  const lookup = useLookup();
  const now = useNow();
  const sorted = useMemo(() => [...(obligations.data ?? [])].sort((a, b) => (a.dueAt < b.dueAt ? -1 : 1)), [obligations.data]);
  const horizon = 60;
  return (
    <div>
      <PageHeader title="Entity protection" actions={<SampleBadge />} />
      <QueryView query={obligations}>
        {() => (
          <div className="space-y-4">
            <Section title="Risk register">
              <QueryView query={risks}>
                {(rs) => (
                  <SimpleTable
                    label="Risk register"
                    rows={rs}
                    getRowId={(r) => r.id}
                    columns={[
                      { id: "risk", header: "Risk", className: "font-medium", cell: (r) => r.title },
                      { id: "likelihood", header: "Likelihood", cell: (r) => <StatusChip tone={r.likelihood === "high" ? "risk" : r.likelihood === "medium" ? "warn" : "neutral"}>{r.likelihood}</StatusChip> },
                      { id: "impact", header: "Impact", cell: (r) => <StatusChip tone={r.impact === "high" ? "risk" : r.impact === "medium" ? "warn" : "neutral"}>{r.impact}</StatusChip> },
                      { id: "owner", header: "Owner", cell: (r) => <PersonChip id={r.owner} /> },
                      { id: "mitigation", header: "Mitigation", className: "text-xs text-muted-foreground", cell: (r) => r.mitigation },
                    ]}
                  />
                )}
              </QueryView>
            </Section>
            <Section title="Next 60 days">
              <div className="relative h-24 overflow-x-auto scrollbar-thin" tabIndex={0} role="img" aria-label="Obligation timeline for the next 60 days">
                <div className="relative h-full min-w-[640px]">
                  <div className="absolute inset-x-0 top-12 h-px bg-border" />
                  {[0, 7, 14, 21, 30, 45, 60].map((dd) => (
                    <div key={dd} className="absolute top-14 -translate-x-1/2 text-[10px] text-muted-foreground" style={{ left: `${(dd / horizon) * 100}%` }}>
                      {dd === 0 ? "today" : `${dd}d`}
                    </div>
                  ))}
                  {sorted
                    .filter((o) => daysUntil(o.dueAt, now) <= horizon)
                    .map((o, i) => (
                      <div key={o.id} className="absolute -translate-x-1/2" style={{ left: `${Math.max(0, Math.min(100, (daysUntil(o.dueAt, now) / horizon) * 100))}%`, top: i % 2 ? 2 : 22 }} title={`${o.title} · ${date(o.dueAt, lookup.tz)}`}>
                        <span className={cn("block size-3 rounded-full ring-2 ring-card", o.status === "green" ? "bg-ok" : o.status === "amber" ? "bg-warn" : "bg-risk")} />
                      </div>
                    ))}
                </div>
              </div>
            </Section>
            <Section title="Obligations">
              <SimpleTable
                label="Obligations"
                rows={sorted}
                getRowId={(o) => o.id}
                rowClassName={(o) => (o.status === "red" ? "bg-risk/5" : undefined)}
                columns={[
                  {
                    id: "title",
                    header: "Obligation",
                    cell: (o) => (
                      <div data-testid={`obligation-${o.id}`}>
                        <div className="font-medium">{o.title}</div>
                        <div className="text-[11px] text-muted-foreground">{o.jurisdiction} · {o.category}</div>
                      </div>
                    ),
                  },
                  { id: "status", header: "Status", cell: (o) => <Status value={o.status} /> },
                  {
                    id: "readiness",
                    header: "Readiness",
                    className: "w-40",
                    cell: (o) => (
                      <div className="flex items-center gap-2">
                        <Progress value={o.readiness} className="h-1.5" aria-label={`Readiness ${o.readiness}%`} />
                        <span className="w-10 text-right text-xs tabular" data-testid="readiness">{o.readiness}%</span>
                      </div>
                    ),
                  },
                  {
                    id: "due",
                    header: "Due",
                    className: "whitespace-nowrap text-xs",
                    cell: (o) => {
                      const d = daysUntil(o.dueAt, now);
                      return (
                        <>
                          <div>{date(o.dueAt, lookup.tz)}</div>
                          <div className={cn("font-medium tabular", d <= 7 ? "text-risk" : d <= 21 ? "text-warn-fg" : "text-muted-foreground")}>{d >= 0 ? `${d} days left` : `${-d} days overdue`}</div>
                        </>
                      );
                    },
                  },
                  {
                    id: "evidence",
                    header: "Evidence",
                    cell: (o) => {
                      const missing = o.requiredEvidence.filter((e) => !e.satisfiedBy);
                      return (
                        <div className="space-y-1 text-xs">
                          {o.requiredEvidence.map((e) => (
                            <div key={e.key} className="flex items-center gap-1.5">
                              {e.satisfiedBy ? <CheckCircle2 className="size-3.5 shrink-0 text-ok" aria-label="provided" /> : <Circle className="size-3.5 shrink-0 text-muted-foreground" aria-label="missing" />}
                              <span className={cn(!e.satisfiedBy && "text-muted-foreground")}>{e.label}</span>
                            </div>
                          ))}
                          {missing.length > 0 && (
                            <Link href="/l1/evidence" className="inline-block text-primary hover:underline">
                              {missing.length} missing
                            </Link>
                          )}
                        </div>
                      );
                    },
                  },
                  { id: "dri", header: "DRI", cell: (o) => <PersonChip id={o.dri} /> },
                ]}
              />
            </Section>
          </div>
        )}
      </QueryView>
    </div>
  );
}
