"use client";

import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { TrendCard } from "@/contracts";
import { Button } from "@/components/ui/button";
import { EmptyState, PageHeader, QueryView } from "@/components/brain/primitives";
import { useHumans, useOp, useTrends } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

/** Unusual weeks, one card at a time. Spikes already marked as known stay hidden. */
export function Trends() {
  const trends = useTrends();
  return (
    <div>
      <PageHeader title="Trends" description="Weeks that look unusual." />
      <QueryView query={trends} isEmpty={(ts) => !ts.some((t) => t.status === "new")} empty={<EmptyState title="No unusual weeks" />}>
        {(ts) => <Pager cards={ts.filter((t) => t.status === "new")} />}
      </QueryView>
    </div>
  );
}

function Pager({ cards }: { cards: TrendCard[] }) {
  const [at, setAt] = useState(0);
  const i = Math.min(at, cards.length - 1);
  const n = cards.length;
  return (
    <section className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{i + 1} of {n}</span>
        <div className="flex gap-2">
          <Button size="icon-sm" variant="outline" disabled={i === 0} onClick={() => setAt(i - 1)} aria-label="Back"><ChevronLeft /></Button>
          <Button size="icon-sm" variant="outline" disabled={i === n - 1} onClick={() => setAt(i + 1)} aria-label="Next"><ChevronRight /></Button>
        </div>
      </div>
      <div key={cards[i].id} className="animate-in fade-in slide-in-from-right-2 duration-300" role="group" aria-roledescription="slide" aria-label={`Trend ${i + 1} of ${n}`}>
        <Card trend={cards[i]} />
      </div>
    </section>
  );
}

function Card({ trend }: { trend: TrendCard }) {
  const humans = useHumans();
  const markKnown = useOp<{ id: string }>("markTrendKnown", { success: "Marked as known" });
  const [showCases, setShowCases] = useState(false);
  const owner = humans.data?.find((h) => h.id === trend.ownerId)?.name ?? trend.ownerId;
  return (
    <div className="space-y-8 rounded-2xl border bg-card p-8">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold">{trend.metric}</h2>
        <p className="text-[15px] text-muted-foreground">{trend.segment}</p>
      </div>
      <Weeks weeks={trend.weeks} />
      <div className="flex items-baseline gap-3">
        <span className="text-4xl font-semibold text-primary">{trend.ratio}×</span>
        <span className="text-[15px] text-muted-foreground">usual · {trend.latest} this week</span>
      </div>
      <p className="text-[15px]">Owner: {owner}</p>
      <div className="flex flex-wrap gap-3">
        <Button variant="outline" onClick={() => setShowCases((v) => !v)}>{showCases ? "Hide the cases" : "See the cases"}</Button>
        <Button onClick={() => markKnown.mutate({ id: trend.id })} disabled={markKnown.isPending}><Check /> Mark as known</Button>
      </div>
      {showCases && (
        <ul className="space-y-2">
          {trend.caseIds.map((id) => (
            <li key={id}>
              <Link href={`/l3/runs/${id}`} className="text-[15px] text-primary hover:underline">{id}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Twelve weekly bars. Only the latest week, the spike, uses the accent colour. */
function Weeks({ weeks }: { weeks: number[] }) {
  const top = Math.max(...weeks, 1);
  return (
    <div className="flex h-28 items-end gap-2" role="img" aria-label={`Weekly counts: ${weeks.join(", ")}`}>
      {weeks.map((count, i) => (
        <div key={i} className={cn("flex-1 rounded-sm", i === weeks.length - 1 ? "bg-primary" : "bg-muted")} style={{ height: `${Math.max(6, (count / top) * 100)}%` }} />
      ))}
    </div>
  );
}
