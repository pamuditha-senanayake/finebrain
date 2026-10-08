"use client";

import { useMemo, useState } from "react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useLookup } from "@/components/brain/names";
import { PageHeader, QueryView, Status } from "@/components/brain/primitives";
import { useSensors, useTemplates } from "@/lib/api/hooks";
import { relTime } from "@/lib/format";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

export function TemplateBoard() {
  const templates = useTemplates();
  const sensors = useSensors();
  const lookup = useLookup();
  const clusterId = useUi((s) => s.clusterId);
  const [filter, setFilter] = useState<"all" | "complete" | "partial" | "stale">("all");
  const sensorName = useMemo(() => new Map((sensors.data ?? []).map((s) => [s.id, s.name])), [sensors.data]);
  const counts = useMemo(() => {
    const list = templates.data ?? [];
    return { all: list.length, complete: list.filter((t) => t.status === "complete").length, partial: list.filter((t) => t.status === "partial").length, stale: list.filter((t) => t.status === "stale").length };
  }, [templates.data]);
  return (
    <div>
      <PageHeader
        title="Template board"
        description="Which templates are complete, partial or stale, which agents filled them, and from which sources."
        actions={
          <ToggleGroup type="single" value={filter} onValueChange={(v) => v && setFilter(v as typeof filter)} variant="outline" size="sm" aria-label="Filter templates">
            {(["all", "complete", "partial", "stale"] as const).map((f) => (
              <ToggleGroupItem key={f} value={f} className="px-2.5 text-xs capitalize">
                {f} <span className="ml-1 text-muted-foreground tabular">{counts[f]}</span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        }
      />
      <QueryView query={templates}>
        {(list) => (
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3">
            {list
              .filter((t) => (filter === "all" || t.status === filter) && (clusterId === "all" || t.clusterId === clusterId))
              .slice(0, 120)
              .map((t) => (
                <li key={t.id} className={cn("rounded-xl border bg-card p-3", t.status === "stale" && "border-risk/40", t.status === "partial" && "border-warn/50")}>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold">{t.name}</h3>
                      <p className="text-[11px] text-muted-foreground">{t.cadence} · owner {lookup.name(t.owner)}</p>
                    </div>
                    <Status value={t.status} />
                  </div>
                  <ul className="mt-2 divide-y text-xs">
                    {t.fields.map((f) => (
                      <li key={f.key} className="grid grid-cols-[1fr_auto] gap-x-2 py-1.5">
                        <span className="truncate">{f.label}</span>
                        <span className={cn("font-mono tabular", !f.value && "text-risk")}>{f.value ?? "missing"}</span>
                        <span className="col-span-2 truncate text-[10px] text-muted-foreground">
                          {f.filledBy ? `${lookup.name(f.filledBy)} · ${f.source ? (sensorName.get(f.source) ?? f.source) : ""} · ${f.filledAt ? relTime(f.filledAt) : ""}` : `needs ${f.sensors.map((s) => sensorName.get(s) ?? s).join(", ") || "a source"}`}
                        </span>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
          </ul>
        )}
      </QueryView>
    </div>
  );
}
