"use client";

import { useMemo, useState } from "react";
import type { Document } from "@/contracts";
import { DataTable, type Column } from "@/components/brain/data-table";
import { useLookup } from "@/components/brain/names";
import { PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { cn } from "@/lib/utils";
import { useDocuments, useFilingRules } from "@/lib/api/hooks";
import { date } from "@/lib/format";

export function LibraryView() {
  const documents = useDocuments();
  const rules = useFilingRules();
  const lookup = useLookup();
  const [category, setCategory] = useState("all");
  const columns: Column<Document>[] = useMemo(
    () => [
      { id: "title", header: "Document", width: "minmax(220px,2fr)", value: (d) => d.title, cell: (d) => <span className="truncate font-medium">{d.title}</span> },
      { id: "category", header: "Category", width: "110px", value: (d) => d.type, cell: (d) => <StatusChip tone="info" className="capitalize">{d.type}</StatusChip> },
      { id: "cluster", header: "Cluster", width: "minmax(120px,1fr)", value: (d) => lookup.cluster(d.clusterId), hideOnMobile: true, cell: (d) => <span className="truncate text-muted-foreground">{lookup.cluster(d.clusterId)}</span> },
      { id: "sens", header: "Sensitivity", width: "110px", value: (d) => d.sensitivity, cell: (d) => <StatusChip tone={d.sensitivity === "restricted" ? "risk" : d.sensitivity === "confidential" ? "warn" : "neutral"}>{d.sensitivity}</StatusChip> },
      { id: "pd", header: "Personal data", width: "100px", value: (d) => (d.personalData ? 1 : 0), hideOnMobile: true, cell: (d) => (d.personalData ? <StatusChip tone="warn">masked</StatusChip> : <span className="text-muted-foreground">none</span>) },
      { id: "extract", header: "Extraction", width: "96px", value: (d) => d.extractionStatus, hideOnMobile: true, cell: (d) => <Status value={d.extractionStatus} /> },
      { id: "facts", header: "Facts", width: "56px", align: "right", value: (d) => d.linkedFacts.length, cell: (d) => d.linkedFacts.length },
      { id: "retention", header: "Retention", width: "88px", align: "right", value: (d) => d.retentionDays, hideOnMobile: true, cell: (d) => `${Math.round(d.retentionDays / 365)}y` },
      { id: "uploaded", header: "Added", width: "100px", value: (d) => d.uploadedAt, hideOnMobile: true, cell: (d) => <span className="text-muted-foreground">{date(d.uploadedAt, lookup.tz)}</span> },
    ],
    [lookup],
  );
  return (
    <div>
      <PageHeader title="Library" description="Every ingested source and document by category, cluster and sensitivity, with extraction status, linked facts and retention." />
      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <QueryView query={documents}>
          {(docs) => {
            const counts = new Map<string, number>();
            for (const d of docs) counts.set(d.type, (counts.get(d.type) ?? 0) + 1);
            const cats = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
            const shown = category === "all" ? docs : docs.filter((d) => d.type === category);
            return (
              <div className="min-w-0 space-y-3">
                <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by category">
                  {[["all", docs.length] as const, ...cats].map(([c, n]) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setCategory(c)}
                      aria-pressed={category === c}
                      className={cn("inline-flex h-7 items-center gap-1.5 rounded-full border px-3 text-xs font-medium capitalize transition-colors hover:bg-accent", category === c && "border-primary bg-primary text-primary-foreground hover:bg-primary/90")}
                    >
                      {c === "all" ? "All categories" : c}
                      <span className={cn("tabular text-[11px]", category === c ? "opacity-80" : "text-muted-foreground")}>{n}</span>
                    </button>
                  ))}
                </div>
                <DataTable label="Documents" data={shown} columns={columns} getRowId={(d) => d.id} initialSort={{ id: "uploaded", desc: true }} height="calc(100dvh - 290px)" searchPlaceholder="Search documents…" />
              </div>
            );
          }}
        </QueryView>
        <Section title="Filing rules" description="Decide where new material lands.">
          <QueryView query={rules} rows={3}>
            {(rs) => (
              <ul className="space-y-2 text-xs">
                {rs.map((r) => (
                  <li key={r.id} className="rounded-lg border p-2">
                    <div className="font-medium">{r.match}</div>
                    <div className="mt-0.5 text-muted-foreground">
                      → {lookup.cluster(r.clusterId)} · {r.type} · {r.sensitivity} · {Math.round(r.retentionDays / 365)} years
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
