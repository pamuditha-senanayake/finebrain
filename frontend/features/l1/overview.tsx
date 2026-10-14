"use client";

import { List, Orbit } from "lucide-react";
import { useCallback, useState } from "react";
import type { BrainMap } from "@/contracts";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useLookup } from "@/components/brain/names";
import { ErrorState, LoadingState, StatusChip } from "@/components/brain/primitives";
import { useBrainMap, useOverview } from "@/lib/api/hooks";
import { pct } from "@/lib/format";
import { cn } from "@/lib/utils";
import { BrainMapView, CLUSTER_PALETTE, type MapSelection } from "./brain-map";
import { MapDetail } from "./map-detail";
import { StatusBox } from "./status-box";

/** L1 home: the whole brain as one map, with a small status box. Charts and tables live on Analytics. */
export function Overview() {
  const map = useBrainMap();
  const overview = useOverview();
  const lookup = useLookup();
  const [view, setView] = useState<"map" | "list">("map");
  const [focusId, setFocusId] = useState<string | null>(null);
  const [selection, setSelection] = useState<MapSelection | null>(null);

  const select = useCallback(
    (s: MapSelection | null) => {
      setSelection(s);
      if (!s || !map.data) return;
      const cluster = s.kind === "cluster" ? s.id : map.data.workflows.find((w) => w.id === (s.kind === "workflow" ? s.id : s.workflowId))?.clusterId;
      if (cluster) setFocusId(cluster);
    },
    [map.data],
  );

  return (
    <div className="relative -mx-3 -my-4 flex flex-col sm:-mx-6 sm:-my-5 lg:block lg:h-[calc(100dvh-3rem)]">
      <h1 className="sr-only">Brain overview</h1>
      <div className="relative h-[68vh] min-h-[420px] lg:absolute lg:inset-0 lg:h-auto">
        {map.isLoading ? (
          <div className="map-surface grid h-full place-items-center"><LoadingState rows={3} label="Loading the brain map" /></div>
        ) : map.error ? (
          <div className="p-4"><ErrorState error={map.error} onRetry={() => map.refetch()} /></div>
        ) : map.data && view === "map" ? (
          <BrainMapView map={map.data} currency={lookup.currency} focusId={focusId} selection={selection} onFocus={setFocusId} onSelect={select} />
        ) : map.data ? (
          <MapList map={map.data} onSelect={(s) => { select(s); }} />
        ) : null}
      </div>

      <div className="pointer-events-none absolute left-3 top-3 z-10 flex">
        <ToggleGroup type="single" value={view} onValueChange={(v) => v && setView(v as "map" | "list")} variant="outline" size="sm" className="pointer-events-auto rounded-full bg-card/80 shadow-sm backdrop-blur" aria-label="View">
          <ToggleGroupItem value="map" aria-label="Map view" className="rounded-l-full px-3"><Orbit /> Map</ToggleGroupItem>
          <ToggleGroupItem value="list" aria-label="List view" className="rounded-r-full px-3"><List /> List</ToggleGroupItem>
        </ToggleGroup>
      </div>

      {selection && map.data && (
        <div className="z-10 p-3 lg:absolute lg:bottom-20 lg:left-3 lg:top-24 lg:w-[300px] lg:p-0">
          <MapDetail map={map.data} selection={selection} currency={lookup.currency} onSelect={select} onClose={() => setSelection(null)} />
        </div>
      )}

      <div className="z-10 p-3 lg:absolute lg:right-3 lg:top-3 lg:w-[236px] lg:p-0">
        {overview.data ? <StatusBox o={overview.data} /> : overview.error ? <ErrorState error={overview.error} onRetry={() => overview.refetch()} /> : <LoadingState rows={4} />}
      </div>
    </div>
  );
}

/** The same brain as an outline, for keyboards, screen readers and quick scanning. */
function MapList({ map, onSelect }: { map: BrainMap; onSelect: (s: MapSelection) => void }) {
  return (
    <div className="map-surface h-full overflow-y-auto px-4 pb-6 pt-16 lg:pr-[264px]">
      <div className="mx-auto grid max-w-4xl gap-3 sm:grid-cols-2">
        {map.clusters.map((c, i) => {
          const wfs = map.workflows.filter((w) => w.clusterId === c.id);
          return (
            <section key={c.id} className="rounded-xl border bg-card/90 p-3 backdrop-blur" style={{ borderTop: `3px solid ${CLUSTER_PALETTE[i % CLUSTER_PALETTE.length]}` }}>
              <button type="button" className="w-full text-left" onClick={() => onSelect({ kind: "cluster", id: c.id })}>
                <h2 className="text-sm font-semibold uppercase tracking-wider">{c.name}</h2>
                <p className="text-[11px] text-muted-foreground">{c.kpi ? `${wfs.length} workflows · ${pct(c.kpi.autonomyRate)} autonomous · ${c.kpi.runs24h} runs today` : "planned"}</p>
              </button>
              {wfs.length > 0 && (
                <ul className="mt-2 space-y-0.5">
                  {wfs.map((w) => (
                    <li key={w.id}>
                      <button type="button" className={cn("flex min-h-7 w-full items-center gap-2 rounded-md px-1.5 text-left text-xs hover:bg-accent")} onClick={() => onSelect({ kind: "workflow", id: w.id })}>
                        <span className="min-w-0 flex-1 truncate">{w.name}</span>
                        {w.health.breaks > 0 && <StatusChip tone="risk" className="h-4 px-1.5 text-[10px]">{w.health.breaks} break{w.health.breaks === 1 ? "" : "s"}</StatusChip>}
                        <span className="text-[10px] text-muted-foreground">{w.items.length} parts</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
