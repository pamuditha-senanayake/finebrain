"use client";

import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import type { Obligation, Risk } from "@/contracts";
import { Progress } from "@/components/ui/progress";
import { CardPager, Folded } from "@/components/brain/card-pager";
import { PersonChip, useLookup } from "@/components/brain/names";
import { EmptyState, PageHeader, QueryView, SampleBadge, StatusChip } from "@/components/brain/primitives";
import { useNow, useObligations, useRisks } from "@/lib/api/hooks";
import { date } from "@/lib/format";
import { daysUntil } from "@/lib/governance/readiness";
import { cn } from "@/lib/utils";

const STATUS = { green: { label: "Ready", tone: "ok" }, amber: { label: "On track", tone: "warn" }, red: { label: "At risk", tone: "risk" } } as const;
const BAR = { green: "[&>[data-slot=progress-indicator]]:bg-ok/80", amber: "[&>[data-slot=progress-indicator]]:bg-warn", red: "[&>[data-slot=progress-indicator]]:bg-risk" };

/** What is due and how ready it is: one obligation at a time, soonest first. Risks wait behind a fold. ?ob= opens on one. */
export function EntityProtection() {
  const obligations = useObligations();
  const risks = useRisks();
  const startAt = useSearchParams().get("ob");
  const sorted = useMemo(() => [...(obligations.data ?? [])].sort((a, b) => (a.dueAt < b.dueAt ? -1 : 1)), [obligations.data]);
  return (
    <div>
      <PageHeader title="Entity protection" description="What is due, and how ready." actions={<SampleBadge />} />
      <QueryView query={obligations} empty={<EmptyState title="Nothing due" />}>
        {() => <CardPager items={sorted} getId={(o) => o.id} render={(o) => <ObligationCard ob={o} />} label="Obligations" startAt={startAt} />}
      </QueryView>
      {risks.data && risks.data.length > 0 && (
        <Folded title={`Risks (${risks.data.length})`}>
          <ul className="space-y-3">{risks.data.map((r) => <RiskLine key={r.id} risk={r} />)}</ul>
        </Folded>
      )}
    </div>
  );
}

function ObligationCard({ ob }: { ob: Obligation }) {
  const lookup = useLookup();
  const now = useNow();
  const left = daysUntil(ob.dueAt, now);
  const missing = ob.requiredEvidence.filter((e) => !e.satisfiedBy).length;
  return (
    <article className="space-y-6 rounded-2xl border bg-card p-8" data-testid={`obligation-${ob.id}`}>
      <div className="space-y-2">
        <StatusChip tone={STATUS[ob.status].tone}>{STATUS[ob.status].label}</StatusChip>
        <h2 className="text-xl font-semibold leading-snug">{ob.title}</h2>
        <p className={cn("text-[15px]", left <= 7 ? "text-risk" : "text-muted-foreground")}>
          Due {date(ob.dueAt, lookup.tz)} · {left >= 0 ? `${left} days left` : `${-left} days overdue`}
        </p>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-4xl font-semibold tabular" data-testid="readiness">{ob.readiness}%</span>
        <Progress value={ob.readiness} className={cn("h-2 flex-1", BAR[ob.status])} aria-label={`Readiness ${ob.readiness}%`} />
      </div>
      <ul className="space-y-2 text-[15px]">
        {ob.requiredEvidence.map((e) => (
          <li key={e.key} className="flex items-center gap-2">
            {e.satisfiedBy ? <CheckCircle2 className="size-4 shrink-0 text-ok" aria-label="proven" /> : <Circle className="size-4 shrink-0 text-muted-foreground" aria-label="missing" />}
            <span className={cn(!e.satisfiedBy && "text-muted-foreground")}>{e.label}</span>
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between">
        <PersonChip id={ob.dri} />
        {missing > 0 && <Link href="/l1/digest?tab=evidence" className="text-[15px] text-primary hover:underline">Add evidence</Link>}
      </div>
    </article>
  );
}

function RiskLine({ risk }: { risk: Risk }) {
  return (
    <li className="rounded-xl border bg-card p-4">
      <p className="text-[15px] font-medium">{risk.title}</p>
      <p className="mt-1 text-[14px] text-muted-foreground">{risk.mitigation}</p>
    </li>
  );
}
