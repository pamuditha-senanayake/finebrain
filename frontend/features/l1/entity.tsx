"use client";

import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";
import { Progress } from "@/components/ui/progress";
import { PersonChip, useLookup } from "@/components/brain/names";
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
      <PageHeader
        title="Entity protection"
        description="Obligations for the legal entity: tax, statutory filings, contracts and renewals, with readiness and missing evidence. The system prepares and collects proof. People file."
        actions={<SampleBadge />}
      />
      <QueryView query={obligations}>
        {() => (
          <div className="space-y-4">
            <Section title="Next 60 days" description="Every date here is sample data and is not legal or tax guidance.">
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
            <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" aria-label="Obligations">
              {sorted.map((o) => {
                const d = daysUntil(o.dueAt, now);
                const missing = o.requiredEvidence.filter((e) => !e.satisfiedBy);
                return (
                  <li key={o.id} className={cn("rounded-xl border bg-card p-3", o.status === "red" && "border-risk/40")} data-testid={`obligation-${o.id}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h3 className="text-sm font-semibold">{o.title}</h3>
                        <p className="text-[11px] text-muted-foreground">{o.jurisdiction} · {o.category}</p>
                      </div>
                      <Status value={o.status} />
                    </div>
                    <div className="mt-3 flex items-center gap-2">
                      <Progress value={o.readiness} className="h-1.5" aria-label={`Readiness ${o.readiness}%`} />
                      <span className="w-10 text-right text-xs tabular" data-testid="readiness">{o.readiness}%</span>
                    </div>
                    <div className="mt-2 flex items-center justify-between text-xs">
                      <span className={cn("font-medium tabular", d <= 7 ? "text-risk" : d <= 21 ? "text-warn-fg" : "text-muted-foreground")}>{d >= 0 ? `${d} days left` : `${-d} days overdue`}</span>
                      <span className="text-muted-foreground">due {date(o.dueAt, lookup.tz)}</span>
                    </div>
                    <ul className="mt-2 space-y-1 text-xs">
                      {o.requiredEvidence.map((e) => (
                        <li key={e.key} className="flex items-center gap-1.5">
                          {e.satisfiedBy ? <CheckCircle2 className="size-3.5 text-ok" aria-label="provided" /> : <Circle className="size-3.5 text-muted-foreground" aria-label="missing" />}
                          <span className={cn(!e.satisfiedBy && "text-muted-foreground")}>{e.label}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="mt-3 flex items-center justify-between text-xs">
                      <span className="inline-flex items-center gap-1">DRI <PersonChip id={o.dri} /></span>
                      {missing.length > 0 && (
                        <Link href="/l1/evidence" className="text-primary hover:underline">
                          {missing.length} missing
                        </Link>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
            <Section title="Risk register">
              <QueryView query={risks}>
                {(rs) => (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                        <tr>
                          <th className="py-1.5 font-medium">Risk</th>
                          <th className="py-1.5 font-medium">Likelihood</th>
                          <th className="py-1.5 font-medium">Impact</th>
                          <th className="py-1.5 font-medium">Owner</th>
                          <th className="py-1.5 font-medium">Mitigation</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rs.map((r) => (
                          <tr key={r.id} className="border-t align-top">
                            <td className="py-2 pr-3 font-medium">{r.title}</td>
                            <td className="py-2 pr-3"><StatusChip tone={r.likelihood === "high" ? "risk" : r.likelihood === "medium" ? "warn" : "neutral"}>{r.likelihood}</StatusChip></td>
                            <td className="py-2 pr-3"><StatusChip tone={r.impact === "high" ? "risk" : r.impact === "medium" ? "warn" : "neutral"}>{r.impact}</StatusChip></td>
                            <td className="py-2 pr-3"><PersonChip id={r.owner} /></td>
                            <td className="py-2 text-xs text-muted-foreground">{r.mitigation}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </QueryView>
            </Section>
          </div>
        )}
      </QueryView>
    </div>
  );
}
