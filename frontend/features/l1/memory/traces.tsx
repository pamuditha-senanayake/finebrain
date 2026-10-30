"use client";

// traces.tsx: every piece of work as a trace, newest first. Filter by area and by flag; 25 at a time with Show more.
// Filters live in the address, so the area card's "See traces" link lands on the right list.
// Used by: app/(l1)/l1/memory/traces/page.tsx. Uses: areas.ts, components/brain, lib/api/hooks.
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import type { TraceSummary } from "@/contracts";
import { CategoryFilter } from "@/components/brain/category-filter";
import { EmptyState, PageHeader, QueryView, SampleBadge } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useMemoryMap, useNow, useTraces } from "@/lib/api/hooks";
import { relTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { AREA_COLOR, AREA_ORDER } from "./areas";
import { NotConnected, notConnected } from "./memory";

// Config
const FLAGS = [
  { value: "all", label: "All" }, { value: "surprise", label: "Surprises" },
  { value: "outside_policy", label: "Outside policy" }, { value: "drift", label: "Drift" },
];

export function Traces() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const map = useMemoryMap();
  const area = params.get("area") ?? "all";
  const flag = params.get("flag") ?? "all";

  // Step 1: a filter change rewrites the address and starts the list from the top
  const setFilter = (field: "area" | "flag", value: string) => {
    const next = new URLSearchParams(params);
    if (value === "all") next.delete(field);
    else next.set(field, value);
    router.replace(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  };

  const names = new Map(map.data?.areas.map((a) => [a.key, a.name]));
  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2"><Link href="/l1/memory"><ArrowLeft /> Living memory</Link></Button>
      <PageHeader title="Traces" eyebrow={map.data?.isSample ? <SampleBadge /> : undefined} description="Each piece of work, from start to end." />
      <div className="flex flex-wrap items-center gap-3">
        <CategoryFilter label="Filter by area" allLabel="All areas" value={area} onChange={(v) => setFilter("area", v)} className="w-[200px] text-[13px]"
          options={AREA_ORDER.map((k) => ({ value: k, count: map.data?.areas.find((a) => a.key === k)?.tracesTotal ?? 0 }))}
          labelOf={(v) => names.get(v as never) ?? v} />
        <ToggleGroup type="single" value={flag} onValueChange={(v) => v && setFilter("flag", v)} variant="outline" size="sm" aria-label="Filter by flag">
          {FLAGS.map((f) => <ToggleGroupItem key={f.value} value={f.value} className="px-3 text-[13px]">{f.label}</ToggleGroupItem>)}
        </ToggleGroup>
      </div>
      {notConnected(map.error) ? <NotConnected /> : <TracePageView key={`${area}-${flag}`} area={area === "all" ? undefined : area} flag={flag === "all" ? undefined : flag} names={names} first />}
    </div>
  );
}

// One page of 25. "Show more" renders the next page under it, so earlier rows never reload.
function TracePageView({ area, flag, cursor, names, first }: { area?: string; flag?: string; cursor?: string; names: Map<string, string>; first?: boolean }) {
  const page = useTraces({ area, flag, cursor });
  const [more, setMore] = useState(false);
  return (
    <QueryView query={page} rows={first ? 8 : 3} isEmpty={(p) => first === true && p.total === 0} empty={<EmptyState title="No traces match" description="Try another area or flag." />}>
      {(p) => (
        <div className="space-y-3">
          {first && <p className="text-[13px] text-muted-foreground">{p.total.toLocaleString()} traces</p>}
          <ul className="divide-y rounded-2xl border bg-card">{p.items.map((t) => <TraceRow key={t.id} trace={t} areaName={names.get(t.area) ?? t.area} />)}</ul>
          {p.nextCursor && !more && <Button variant="outline" onClick={() => setMore(true)}>Show more</Button>}
          {p.nextCursor && more && <TracePageView area={area} flag={flag} cursor={p.nextCursor} names={names} />}
        </div>
      )}
    </QueryView>
  );
}

function TraceRow({ trace, areaName }: { trace: TraceSummary; areaName: string }) {
  const now = useNow();
  const flagged = trace.match === "surprise" || trace.policyCheck === "outside" || trace.drift.length > 0;
  return (
    <li>
      <Link href={`/l1/memory/traces/${trace.id}`} className="flex flex-col gap-1.5 px-5 py-4 hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-ring sm:flex-row sm:items-center sm:gap-4">
        <span className="flex min-w-0 flex-1 items-center gap-2.5">
          <span className="size-2.5 shrink-0 rounded-full" style={{ background: AREA_COLOR[trace.area] }} aria-hidden />
          <span className="truncate text-[15px] font-medium">{trace.subject}</span>
        </span>
        <span className="flex flex-wrap items-center gap-2 text-[13px] text-muted-foreground">
          <span>{areaName}</span>
          <span aria-hidden>·</span>
          <span>{trace.outcome}</span>
          {trace.source === "outside" && <span className="rounded-full border px-2">Outside Finebrain</span>}
          {flagged && <span className={cn("rounded-full bg-primary/12 px-2 font-medium text-primary")}>{flagLabel(trace)}</span>}
          <span className="tabular-nums">{relTime(trace.startedAt, now)}</span>
        </span>
      </Link>
    </li>
  );
}

function flagLabel(t: TraceSummary) {
  if (t.drift.length) return `${t.drift[0]} drift`;
  if (t.policyCheck === "outside") return "Outside policy";
  return "Surprise";
}
