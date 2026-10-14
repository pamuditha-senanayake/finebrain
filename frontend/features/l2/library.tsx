"use client";

import { useMemo, useState } from "react";
import type { Document } from "@/contracts";
import { DataTable, type Column } from "@/components/brain/data-table";
import { CategoryFilter, countBy } from "@/components/brain/category-filter";
import { useLookup } from "@/components/brain/names";
import { SimpleTable } from "@/components/brain/simple-table";
import { PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useDocuments, useFilingRules } from "@/lib/api/hooks";
import { date } from "@/lib/format";

export function LibraryView() {
  const documents = useDocuments();
  const rules = useFilingRules();
  const lookup = useLookup();
  const [category, setCategory] = useState("all");
  const columns: Column<Document>[] = useMemo(
    () => [
      { id: "title", header: "Document", width: "minmax(240px,2.4fr)", value: (d) => d.title, cell: (d) => <div className="min-w-0"><div className="truncate font-medium" title={d.title}>{d.title}</div><div className="mt-0.5 truncate text-[11px] text-muted-foreground">{lookup.cluster(d.clusterId)} · added {date(d.uploadedAt, lookup.tz)}</div></div> },
      { id: "category", header: "Category", width: "110px", value: (d) => d.type, cell: (d) => <StatusChip tone="info" className="capitalize">{d.type}</StatusChip> },
      { id: "sens", header: "Sensitivity", width: "110px", value: (d) => d.sensitivity, cell: (d) => <StatusChip tone={d.sensitivity === "restricted" ? "risk" : d.sensitivity === "confidential" ? "warn" : "neutral"}>{d.sensitivity}</StatusChip> },
      { id: "pd", header: "Personal", width: "92px", value: (d) => (d.personalData ? 1 : 0), hideOnMobile: true, cell: (d) => (d.personalData ? <StatusChip tone="warn">masked</StatusChip> : <span className="text-muted-foreground">none</span>) },
      { id: "extract", header: "Extraction", width: "96px", value: (d) => d.extractionStatus, hideOnMobile: true, cell: (d) => <Status value={d.extractionStatus} /> },
      { id: "facts", header: "Facts", width: "56px", align: "right", value: (d) => d.linkedFacts.length, cell: (d) => d.linkedFacts.length },
      { id: "retention", header: "Retention", width: "88px", align: "right", value: (d) => d.retentionDays, hideOnMobile: true, cell: (d) => `${Math.round(d.retentionDays / 365)}y` },
    ],
    [lookup],
  );
  return (
    <div>
      <PageHeader title="Library" description="Every ingested source and document by category, cluster and sensitivity, with extraction status, linked facts and retention." />
      <div className="space-y-12">
        <QueryView query={documents}>
          {(docs) => {
            const shown = category === "all" ? docs : docs.filter((d) => d.type === category);
            return (
              <DataTable
                rowHeight={58}
                label="Documents"
                data={shown}
                columns={columns}
                getRowId={(d) => d.id}
                initialSort={{ id: "uploaded", desc: true }}
                height={560}
                searchPlaceholder="Search documents…"
                toolbar={<CategoryFilter label="Filter by category" allLabel="All categories" value={category} onChange={setCategory} options={countBy(docs, (d) => d.type)} />}
              />
            );
          }}
        </QueryView>
        <Section plain title="Filing rules" description="Decide where new material lands.">
          <QueryView query={rules} rows={3}>
            {(rs) => (
              <SimpleTable
                label="Filing rules"
                rows={rs}
                getRowId={(r) => r.id}
                columns={[
                  { id: "match", header: "Matches", className: "font-medium", cell: (r) => r.match },
                  { id: "cluster", header: "Cluster", cell: (r) => lookup.cluster(r.clusterId) },
                  { id: "type", header: "Category", cell: (r) => <StatusChip tone="info" className="capitalize">{r.type}</StatusChip> },
                  { id: "sens", header: "Sensitivity", cell: (r) => r.sensitivity },
                  { id: "ret", header: "Retention", align: "right", cell: (r) => `${Math.round(r.retentionDays / 365)} years` },
                ]}
              />
            )}
          </QueryView>
        </Section>
      </div>
    </div>
  );
}
