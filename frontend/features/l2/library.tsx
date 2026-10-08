"use client";

import { useMemo } from "react";
import type { Document } from "@/contracts";
import { DataTable, type Column } from "@/components/brain/data-table";
import { useLookup } from "@/components/brain/names";
import { PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useDocuments, useFilingRules } from "@/lib/api/hooks";
import { date } from "@/lib/format";

export function LibraryView() {
  const documents = useDocuments();
  const rules = useFilingRules();
  const lookup = useLookup();
  const columns: Column<Document>[] = useMemo(
    () => [
      { id: "title", header: "Document", width: "minmax(220px,2fr)", value: (d) => d.title, cell: (d) => <span className="truncate font-medium">{d.title}</span> },
      { id: "cluster", header: "Cluster", width: "minmax(120px,1fr)", value: (d) => lookup.cluster(d.clusterId), hideOnMobile: true, cell: (d) => <span className="truncate text-muted-foreground">{lookup.cluster(d.clusterId)}</span> },
      { id: "type", header: "Type", width: "90px", value: (d) => d.type, hideOnMobile: true, cell: (d) => d.type },
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
      <PageHeader title="Library" description="Every ingested source and document by cluster, type and sensitivity, with extraction status, linked facts and retention." />
      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <QueryView query={documents}>
          {(docs) => <DataTable label="Documents" data={docs} columns={columns} getRowId={(d) => d.id} initialSort={{ id: "uploaded", desc: true }} height="calc(100dvh - 240px)" />}
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
