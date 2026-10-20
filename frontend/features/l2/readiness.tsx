"use client";

import { AlarmClock, Bot, KeyRound, Mail } from "lucide-react";
import Link from "next/link";
import type { ReadinessGap, ReadinessRule } from "@/contracts";
import { Button } from "@/components/ui/button";
import { CardPager, Folded } from "@/components/brain/card-pager";
import { PersonChip, useLookup } from "@/components/brain/names";
import { EmptyState, PageHeader, QueryView, SampleBadge, StatusChip } from "@/components/brain/primitives";
import { useGaps, useOp, useReadinessRules } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { date, relTime } from "@/lib/format";

const ACTION = {
  dispatch_agent: { label: "Send an agent", icon: Bot, tone: "agent" as const },
  request_dri: { label: "Ask the owner", icon: Mail, tone: "warn" as const },
  request_grant: { label: "Ask for a data source", icon: KeyRound, tone: "risk" as const },
};

/** What proof is missing, one gap at a time, with the next move for each. Rules are folded: they rarely change. */
export function Readiness() {
  const rules = useReadinessRules();
  const gaps = useGaps();
  const { user } = useCurrentUser();
  const run = useOp("runReadinessScheduler", { success: "Checked. Gaps are up to date." });
  return (
    <div>
      <PageHeader
        title="Readiness"
        description="What proof is missing."
        actions={
          <div className="flex items-center gap-2">
            <SampleBadge />
            <Button onClick={() => run.mutate({})} disabled={run.isPending || !user || user.tier === "L3"} data-testid="run-scheduler">
              <AlarmClock /> Check now
            </Button>
          </div>
        }
      />
      <QueryView query={gaps} empty={<EmptyState title="No gaps" description="Everything due is proven." />}>
        {(gs) => <CardPager items={gs} getId={(g) => g.id} render={(g) => <GapCard gap={g} />} label="Gaps" testId="gaps" />}
      </QueryView>
      {rules.data && rules.data.length > 0 && (
        <Folded title={`Rules (${rules.data.length})`}>
          <ul className="space-y-3">{rules.data.map((r) => <RuleLine key={r.id} rule={r} />)}</ul>
        </Folded>
      )}
    </div>
  );
}

function GapCard({ gap }: { gap: ReadinessGap }) {
  const lookup = useLookup();
  const a = ACTION[gap.action];
  return (
    <article className="space-y-6 rounded-2xl border bg-card p-8">
      <div className="space-y-2">
        <StatusChip tone={a.tone}>
          <a.icon className="size-3.5" aria-hidden /> {a.label}
        </StatusChip>
        <h2 className="text-xl font-semibold leading-snug">{gap.missing}</h2>
        <p className="text-[15px] text-muted-foreground">
          {gap.target.label} · due {date(gap.dueAt, lookup.tz)}
        </p>
      </div>
      <div className="flex items-center justify-between">
        <PersonChip id={gap.dri} />
        {gap.requestId && (
          <Link href={`/l1/digest?tab=evidence&req=${gap.requestId}`} className="text-[15px] text-primary hover:underline">
            Request sent
          </Link>
        )}
      </div>
    </article>
  );
}

function RuleLine({ rule }: { rule: ReadinessRule }) {
  return (
    <li className="rounded-xl border bg-card p-4">
      <p className="text-[15px] font-medium">{rule.target}</p>
      <p className="mt-1 text-[14px] text-muted-foreground">{rule.requires}</p>
      <p className="mt-1 text-[13px] text-muted-foreground">
        {rule.checkEvery} · last run {relTime(rule.lastRunAt)}
      </p>
    </li>
  );
}
