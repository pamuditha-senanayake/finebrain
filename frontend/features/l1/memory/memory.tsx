"use client";

// memory.tsx: the Living memory page. The whole page is the globe; the title sits top left, four figures in a small
// panel top right, the area legend bottom left, and a chosen area's card slides in on the right. On a phone the globe
// takes the top and the legend and card follow below. The chosen area lives in the address (?area=).
// Used by: app/(l1)/l1/memory/page.tsx. Uses: globe-canvas.tsx, globe-flat.tsx, area-card.tsx, areas.ts, lib/api/hooks.
import { useReducedMotion } from "motion/react";
import { useTheme } from "next-themes";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { lazy, Suspense, useState, type ReactNode } from "react";
import type { AreaKey, MemoryMap } from "@/contracts";
import { AreaKey as AreaKeys } from "@/contracts";
import { EmptyState, ErrorState, SampleBadge } from "@/components/brain/primitives";
import { ApiError } from "@/lib/api/client";
import { useMemoryMap } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { AreaCard } from "./area-card";
import { AREA_COLOR, AREA_ORDER, areaLabel, driftTotal } from "./areas";
import GlobeFlat from "./globe-flat";

// React.lazy, so three.js loads only when the globe is shown, never on route prefetch.
const GlobeCanvas = lazy(() => import("./globe-canvas"));

/** A workspace without the trace store yet (a real tenant before stage 7): the map answers 501 "not connected yet",
 * and the paths under it answer 404. */
export function notConnected(error: unknown) {
  return error instanceof ApiError && (error.status === 501 || error.status === 404);
}

export function NotConnected() {
  return <EmptyState title="Not connected yet" description="This workspace has no trace store yet. The demo workspace shows sample data." />;
}

function canUseWebGL() {
  try {
    return !!document.createElement("canvas").getContext("webgl2");
  } catch {
    return false;
  }
}

export function LivingMemory() {
  const map = useMemoryMap();
  // Step 1: pick what fills the page: the globe, or a designed state
  let body: ReactNode;
  if (map.isLoading) body = <div className="absolute inset-0 m-auto size-[min(60vh,60vw)] animate-pulse rounded-full bg-muted" role="status" aria-label="Loading" />;
  else if (notConnected(map.error)) body = <Centre><NotConnected /></Centre>;
  else if (map.error) body = <Centre><ErrorState error={map.error} onRetry={() => map.refetch()} /></Centre>;
  else if (!map.data || map.data.areas.every((a) => a.tracesTotal === 0)) body = <Centre><EmptyState title="No traces yet" description="They appear after the first run." /></Centre>;
  else body = <Scene map={map.data} />;

  return (
    <div className="relative -mx-3 -my-4 flex min-h-[calc(100dvh-3rem)] flex-col overflow-x-clip bg-[radial-gradient(ellipse_at_center,var(--card)_0%,var(--background)_70%)] sm:-mx-6 sm:-my-5 sm:block sm:h-[calc(100dvh-3rem)] sm:overflow-hidden">
      <header className="pointer-events-none relative z-10 px-5 pt-5 sm:absolute sm:left-0 sm:top-0">
        {map.data?.isSample && <SampleBadge />}
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Living memory</h1>
        <p className="text-[15px] text-muted-foreground">Where work happens, and whether it still holds.</p>
      </header>
      {body}
    </div>
  );
}

function Centre({ children }: { children: ReactNode }) {
  return <div className="flex flex-1 items-center justify-center p-6 sm:absolute sm:inset-0"><div className="w-full max-w-md">{children}</div></div>;
}

function Scene({ map }: { map: MemoryMap }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const parsed = AreaKeys.safeParse(params.get("area"));
  const selected = parsed.success ? parsed.data : null;
  const reduced = useReducedMotion();
  const [webgl] = useState(canUseWebGL);
  const { resolvedTheme } = useTheme();

  // Step 2: choosing an area writes it to the address; choosing it again closes the card
  const choose = (key: AreaKey | null) => {
    const next = new URLSearchParams(params);
    if (key && key !== selected) next.set("area", key);
    else next.delete("area");
    router.replace(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  };

  return (
    <>
      {/* The globe fills the page above the legend and left of the right-hand column, and moves left when a card opens */}
      <section className={cn("relative h-[58dvh] sm:absolute sm:bottom-[104px] sm:left-0 sm:right-[320px] sm:top-0 sm:h-auto", selected && "sm:right-[440px]")} aria-label="The globe of areas">
        {reduced || !webgl ? <GlobeFlat areas={map.areas} selected={selected} onSelect={choose} /> : (
          <Suspense fallback={<div className="absolute inset-0 m-auto size-[min(60vh,60vw)] animate-pulse rounded-full bg-muted" />}>
            <GlobeCanvas areas={map.areas} selected={selected} onSelect={choose} theme={resolvedTheme ?? "light"} />
          </Suspense>
        )}
      </section>
      <Legend map={map} selected={selected} onSelect={choose} />
      {/* One right-hand column: the figures, then the chosen area's card below them, scrolling on its own */}
      <div className="relative z-10 flex flex-col gap-3 px-3 pb-6 sm:pointer-events-none sm:absolute sm:bottom-5 sm:right-5 sm:top-5 sm:w-[420px] sm:items-end sm:px-0 sm:pb-0">
        <Figures map={map} />
        {selected && (
          <div className="w-full sm:pointer-events-auto sm:min-h-0 sm:flex-1 sm:overflow-y-auto">
            <AreaCard areaKey={selected} onClose={() => choose(null)} onPick={choose} />
          </div>
        )}
      </div>
    </>
  );
}

// The four figures, small and together, so the globe keeps the page.
function Figures({ map }: { map: MemoryMap }) {
  const { skill, policy, security } = map.totals.drift;
  const drift = skill + policy + security;
  return (
    <section aria-label="This week" className="grid w-full grid-cols-2 gap-x-5 gap-y-3 rounded-2xl border bg-card/85 p-4 shadow-sm backdrop-blur sm:pointer-events-auto sm:w-[300px]">
      <Figure label="Traces this week" value={map.totals.traces7d.toLocaleString()} />
      <Figure label="Patterns" value={String(map.totals.patterns)} />
      <Figure label="Drift" value={String(drift)} accent={drift > 0} hint={drift ? [skill && `${skill} skill`, policy && `${policy} policy`, security && `${security} access`].filter(Boolean).join(" · ") : "None"} />
      <Figure label="Waiting" value={String(map.totals.surprises)} hint="to review" />
    </section>
  );
}

function Figure({ label, value, hint, accent }: { label: string; value: string; hint?: string; accent?: boolean }) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-[0.07em] text-muted-foreground">{label}</p>
      <p className={cn("text-xl font-semibold tabular-nums", accent && "text-primary")}>{value}</p>
      {hint && <p className="text-[12px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

// Every area as a chip along the bottom: the keyboard and screen reader way in, and the key to the globe's colours.
// Chips keep the sides of the page free, so every label on the globe has room.
function Legend({ map, selected, onSelect }: { map: MemoryMap; selected: AreaKey | null; onSelect: (key: AreaKey) => void }) {
  return (
    <nav aria-label="Areas" className={cn("relative z-10 px-3 py-4 sm:absolute sm:bottom-5 sm:left-5 sm:right-[340px] sm:p-0", selected && "sm:right-[460px]")}>
      <ul className="flex flex-wrap gap-2">
        {AREA_ORDER.map((key) => {
          const area = map.areas.find((a) => a.key === key);
          if (!area) return null;
          const drift = driftTotal(area);
          return (
            <li key={key}>
              <button type="button" onClick={() => onSelect(key)} aria-pressed={selected === key} aria-label={areaLabel(area)}
                className={cn("flex items-center gap-2 rounded-full border bg-card/85 px-3 py-1.5 text-[14px] shadow-sm backdrop-blur hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring", selected === key && "border-foreground/40 bg-muted font-medium")}>
                <span className="size-2.5 shrink-0 rounded-full" style={{ background: AREA_COLOR[key] }} aria-hidden />
                <span>{area.name}</span>
                <span className="tabular-nums text-muted-foreground">{area.traces7d}</span>
                {drift > 0 && <span className="rounded-full bg-primary px-1.5 text-[12px] font-semibold text-primary-foreground">{drift}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
