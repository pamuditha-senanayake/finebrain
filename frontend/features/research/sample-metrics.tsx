"use client";

// A paper with no Lab run yet: its sample metrics, marked SAMPLE and never exportable, or results imported from the
// research execution repository. Monitoring only; nothing here can change the product.
import { Download, FileUp } from "lucide-react";
import { useRef, useState } from "react";
import { EXPORTABLE_PROVENANCE, type ResearchPaper, type ResearchSnapshot } from "@/contracts/research";
import { EmptyState, QueryView, SampleBadge, Section } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { useResearch } from "@/lib/api/hooks";
import { parseExperimentOutput, toCsv } from "./import-adapter";

function shown(value: number, unit: string) {
  if (unit === "ratio") return `${(value * 100).toFixed(1)}%`;
  if (unit === "percent") return `${value.toFixed(1)}%`;
  if (unit === "ms") return `${value} ms`;
  return value.toLocaleString();
}

function save(name: string, body: string, type: string) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([body], { type }));
  link.download = name;
  link.click();
}

export function SampleMetrics({ paper }: { paper: ResearchPaper }) {
  const research = useResearch();
  const [imported, setImported] = useState<ResearchSnapshot[] | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const readFile = async (file: File | undefined) => {
    if (!file) return;
    const parsed = parseExperimentOutput(JSON.parse(await file.text()));
    if (parsed.ok) setImported(parsed.snapshots);
    setImportError(parsed.ok ? null : parsed.error);
  };

  return (
    <QueryView query={research} empty={<EmptyState title="No sample data" description="Run an experiment in the Lab to see results here." />}>
      {(snapshots) => {
        const snapshot = (imported ?? snapshots).find((s) => s.paper === paper);
        if (!snapshot) return <EmptyState title="No results for this paper yet" description="Run an experiment in the Lab, or import results." />;
        // A sample value is never exported as a result, even inside an imported snapshot
        const exportable = !snapshot.isSample && snapshot.metrics.every((m) => EXPORTABLE_PROVENANCE.includes(m.provenance));
        return (
          <Section
            title={<span className="inline-flex items-center gap-2">{imported ? "Imported results" : "Sample metrics"} {snapshot.isSample && <SampleBadge />}</span>}
            description={snapshot.isSample ? "Made-up values for design work. They can never be exported." : snapshot.source}
            actions={
              <div className="flex flex-wrap gap-2">
                <input ref={fileRef} type="file" accept="application/json" className="sr-only" aria-label="Import results" onChange={(e) => readFile(e.target.files?.[0])} />
                <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()}><FileUp /> Import results</Button>
                <Button size="sm" variant="outline" disabled={!exportable} title={exportable ? undefined : "Sample values cannot be exported"}
                  onClick={() => save(`research-${snapshot.paper}.csv`, toCsv([snapshot]), "text/csv")}><Download /> CSV</Button>
              </div>
            }
          >
            {importError && <p role="alert" className="mb-3 text-[15px] text-risk">Import failed: {importError}</p>}
            <ul className="divide-y">
              {snapshot.metrics.map((metric) => (
                <li key={metric.key}>
                  <details className="group py-3">
                    <summary className="flex cursor-pointer list-none items-baseline justify-between gap-4 text-[15px]">
                      <span>{metric.label}</span>
                      <span className="font-semibold tabular">{shown(metric.value, metric.unit)}</span>
                    </summary>
                    <p className="mt-2 text-[13px] text-muted-foreground">{metric.definition} Condition: {metric.condition}.</p>
                  </details>
                </li>
              ))}
            </ul>
          </Section>
        );
      }}
    </QueryView>
  );
}
