"use client";

// surprises.tsx: the "New ways" tab of To review. Work that matched no known pattern waits here, one at a time, for a
// steward or leader to keep it as normal; until then it counts as a surprise. The trace shows the whole story.
// Used by: features/l1/digest.tsx. Uses: memory-actions.tsx (ConfirmSurprise), components/brain (CardPager), lib/api/hooks.
import Link from "next/link";
import type { TraceSummary } from "@/contracts";
import { CardPager } from "@/components/brain/card-pager";
import { EmptyState, QueryView } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { useMemoryMap, useTraces } from "@/lib/api/hooks";
import { dateTime } from "@/lib/format";
import { AREA_COLOR } from "./areas";
import { ConfirmSurprise } from "./memory-actions";
import { notConnected } from "./memory";

/** How many surprises wait, for the tab's count; 0 when the memory is not connected. */
export function useSurpriseCount() {
  return useTraces({ flag: "surprise" }).data?.total ?? 0;
}

export function Surprises() {
  const map = useMemoryMap();
  const page = useTraces({ flag: "surprise" });
  const names = new Map((map.data?.areas ?? []).map((a) => [a.key, a.name]));
  if (notConnected(page.error)) return <EmptyState title="Living memory is not connected" description="New ways of working show here once this workspace keeps traces." />;
  return (
    <div className="space-y-4">
      <p className="text-[15px] text-muted-foreground">Work that matched no known pattern. Keep it if it is how the company works now.</p>
      <QueryView query={page} rows={4} isEmpty={(p) => p.items.length === 0}
        empty={<EmptyState title="Nothing new" description="Work that matches no known pattern shows here." />}>
        {(p) => <CardPager items={p.items} getId={(t) => t.id} label="New way of working" testId="surprise-pager"
          render={(t) => <SurpriseCard trace={t} areaName={names.get(t.area) ?? t.area} sample={!!map.data?.isSample} />} />}
      </QueryView>
    </div>
  );
}

function SurpriseCard({ trace, areaName, sample }: { trace: TraceSummary; areaName: string; sample: boolean }) {
  return (
    <div className="space-y-5 rounded-2xl border bg-card p-6">
      <div className="space-y-1.5">
        <p className="flex items-center gap-2 text-[13px] text-muted-foreground">
          <span className="size-2.5 rounded-full" style={{ background: AREA_COLOR[trace.area] }} aria-hidden />
          {areaName} · {dateTime(trace.startedAt)}
        </p>
        <h3 className="text-lg font-semibold">{trace.subject}</h3>
        <p className="text-[15px] text-muted-foreground">Ended: {trace.outcome}{trace.source === "outside" ? " · done outside Finebrain" : ""}</p>
      </div>
      <Button asChild variant="outline"><Link href={`/l1/memory/traces/${trace.id}`}>Open the trace</Link></Button>
      <ConfirmSurprise traceId={trace.id} sample={sample} />
    </div>
  );
}
