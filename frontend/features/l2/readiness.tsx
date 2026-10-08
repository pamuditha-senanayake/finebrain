"use client";

import { AlarmClock, Bot, KeyRound, Mail } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { PersonChip, useLookup } from "@/components/brain/names";
import { EmptyState, PageHeader, QueryView, SampleBadge, Section, StatusChip } from "@/components/brain/primitives";
import { useGaps, useOp, useReadinessRules } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { date, relTime } from "@/lib/format";

const ACTION = {
  dispatch_agent: { label: "Dispatch an agent to fetch it", icon: Bot, tone: "agent" as const },
  request_dri: { label: "Request it from the DRI", icon: Mail, tone: "warn" as const },
  request_grant: { label: "Request permission to a new source", icon: KeyRound, tone: "risk" as const },
};

export function Readiness() {
  const rules = useReadinessRules();
  const gaps = useGaps();
  const lookup = useLookup();
  const { user } = useCurrentUser();
  const run = useOp("runReadinessScheduler", { success: "Scheduler ran. Gaps and requests are up to date." });
  return (
    <div>
      <PageHeader
        title="Readiness scheduler"
        description="Rules compare what each obligation, template and loop requires with what exists. Each gap gets an action. Requests start early and escalate as deadlines approach."
        actions={
          <div className="flex items-center gap-2">
            <SampleBadge />
            <Button onClick={() => run.mutate({})} disabled={run.isPending || !user || user.tier === "L3"} data-testid="run-scheduler">
              <AlarmClock /> Run scheduler now
            </Button>
          </div>
        }
      />
      <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Section title="Gaps" description="Found on the last run">
          <QueryView query={gaps} empty={<EmptyState title="No gaps yet" description="Run the scheduler to compare required and available evidence." />}>
            {(gs) => (
              <ul className="divide-y" data-testid="gaps">
                {gs.map((g) => {
                  const a = ACTION[g.action];
                  return (
                    <li key={g.id} className="flex flex-wrap items-start gap-3 py-2.5">
                      <a.icon className="mt-0.5 size-4 text-muted-foreground" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium">{g.missing}</div>
                        <div className="text-xs text-muted-foreground">
                          {g.target.label} · due {date(g.dueAt, lookup.tz)} · escalates at {g.escalationDays.join(", ")} days
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <StatusChip tone={a.tone}>{a.label}</StatusChip>
                        <span className="text-[11px]"><PersonChip id={g.dri} /></span>
                        {g.requestId && <Link href="/l1/evidence" className="text-[11px] text-primary hover:underline">request sent</Link>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </QueryView>
        </Section>
        <Section title="Rules">
          <QueryView query={rules} rows={3}>
            {(rs) => (
              <ul className="space-y-2">
                {rs.map((r) => (
                  <li key={r.id} className="rounded-lg border p-2.5 text-sm">
                    <div className="font-medium">{r.target}</div>
                    <div className="text-xs text-muted-foreground">{r.requires}</div>
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      {r.checkEvery} · escalate at {r.escalationDays.join(", ")} days · last run {relTime(r.lastRunAt)}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </Section>
      </div>
    </div>
  );
}
