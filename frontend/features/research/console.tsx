"use client";

import { useReducedMotion } from "motion/react";
// Research Console. Monitoring only, read only, removable. Product code must never import from this folder.
import { Download, FileUp, FlaskConical } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState } from "react";
import { Line, LineChart, XAxis, YAxis } from "recharts";
import type { ResearchPaper, ResearchSnapshot } from "@/contracts/research";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChartContainer } from "@/components/ui/chart";
import { PageHeader, QueryView, Section } from "@/components/brain/primitives";
import { useResearch } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { parseExperimentOutput, toCsv } from "./import-adapter";

const PAPERS: { key: ResearchPaper; label: string }[] = [
  { key: "skills", label: "Skills" },
  { key: "policies", label: "Policies" },
  { key: "security", label: "Security" },
  { key: "integration", label: "Integration" },
];

function fmt(v: number, unit: string) {
  if (unit === "ratio") return `${(v * 100).toFixed(1)}%`;
  if (unit === "percent") return `${v.toFixed(1)}%`;
  if (unit === "ms") return `${v} ms`;
  return v.toLocaleString();
}

function save(name: string, body: string, type: string) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([body], { type }));
  a.download = name;
  a.click();
}

export function ResearchConsole() {
  const reduceMotion = useReducedMotion();
  const params = useParams<{ paper?: string }>();
  const paper = (params.paper as ResearchPaper | undefined) ?? "skills";
  const research = useResearch();
  const [imported, setImported] = useState<ResearchSnapshot[] | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <div>
      <PageHeader
        eyebrow={<span className="inline-flex items-center gap-1"><FlaskConical className="size-3" /> Research Console · monitoring only</span>}
        title="Research metrics"
        description="Aggregates the same events the product records into research metrics for the four paper program. Nothing here can change the product."
        actions={
          <div className="flex flex-wrap gap-2">
            <input
              ref={fileRef}
              type="file"
              accept="application/json"
              className="sr-only"
              aria-label="Import results"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                const res = parseExperimentOutput(JSON.parse(await f.text()));
                if (res.ok) {
                  setImported(res.snapshots);
                  setImportError(null);
                } else setImportError(res.error);
              }}
            />
            <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()}>
              <FileUp /> Import results
            </Button>
          </div>
        }
      />
      <nav className="mb-4 flex gap-1 border-b" aria-label="Papers">
        {PAPERS.map((p) => (
          <Link key={p.key} href={`/research/${p.key}`} aria-current={p.key === paper ? "page" : undefined} className={cn("-mb-px border-b-2 px-3 py-2 text-sm", p.key === paper ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:text-foreground")}>
            {p.label}
          </Link>
        ))}
      </nav>
      {importError && <p className="mb-3 text-sm text-risk">Import failed: {importError}</p>}
      <QueryView query={research}>
        {(snaps) => {
          const all = imported ?? snaps;
          const s = all.find((x) => x.paper === paper) ?? all[0];
          const exportable = !s.isSample;
          return (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold">{s.title}</h2>
                {s.isSample && <Badge className="bg-warn text-black">SAMPLE</Badge>}
                <span className="text-xs text-muted-foreground">{s.source} · {s.takenAt.slice(0, 16).replace("T", " ")} UTC</span>
                <div className="ml-auto flex gap-2">
                  <Button size="sm" variant="outline" disabled={!exportable} onClick={() => save(`research-${s.paper}.csv`, toCsv([s]), "text/csv")}>
                    <Download /> CSV
                  </Button>
                  <Button size="sm" variant="outline" disabled={!exportable} onClick={() => save(`research-${s.paper}.json`, JSON.stringify(s, null, 2), "application/json")}>
                    <Download /> JSON
                  </Button>
                </div>
              </div>
              {!exportable && <p className="text-xs text-muted-foreground">Sample values can never be exported as results. Import real experiment output to enable export.</p>}
              <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {s.metrics.map((m) => (
                  <li key={m.key}>
                    <Section title={m.label} description={m.condition}>
                      <div className="flex items-end justify-between gap-2">
                        <div className="text-2xl font-semibold tabular">
                          {fmt(m.value, m.unit)}
                          {s.isSample && <span className="ml-1 align-top text-[10px] font-semibold text-warn-fg">SAMPLE</span>}
                        </div>
                        <ChartContainer config={{ y: { label: m.label, color: "var(--chart-2)" } }} className="h-12 w-28">
                          <LineChart data={m.series}>
                            <XAxis dataKey="x" hide />
                            <YAxis hide domain={["auto", "auto"]} />
                            <Line isAnimationActive={!reduceMotion} dataKey="y" stroke="var(--color-y)" dot={false} strokeWidth={1.5} />
                          </LineChart>
                        </ChartContainer>
                      </div>
                      <p className="mt-2 text-[11px] text-muted-foreground">{m.definition}</p>
                    </Section>
                  </li>
                ))}
              </ul>
            </div>
          );
        }}
      </QueryView>
    </div>
  );
}
