"use client";

// Research home: the four papers, one row each, with the latest verdict and where its evidence comes from.
import { ChevronRight, FlaskConical, Lock } from "lucide-react";
import Link from "next/link";
import type { LabExperiment } from "@/contracts/research";
import { PageHeader, StatusChip } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { useExperiments, useResults } from "./lab-api";
import { PAPERS, VerdictChip } from "./lab-ui";

const READABLE = new Set(["finished", "invalid_run", "budget_reached"]);

export function latestFor(experiments: LabExperiment[] | undefined, paper: string): LabExperiment | null {
  return (experiments ?? []).find((e) => e.paper === paper && READABLE.has(e.status)) ?? null;
}

export function ResearchHome() {
  const experiments = useExperiments();
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow={<span className="inline-flex items-center gap-1"><FlaskConical className="size-3" /> Research</span>}
        title="Research"
        description="Four papers. Each result is judged against thresholds locked before its run."
        actions={
          <>
            <Button asChild variant="outline"><Link href="/research/prereg"><Lock /> Preregistrations</Link></Button>
            <Button asChild><Link href="/research/lab">Open the Lab</Link></Button>
          </>
        }
      />
      <ul className="space-y-3" aria-label="Papers">
        {PAPERS.map((paper) => (
          <li key={paper.key}>
            <PaperRow paper={paper} latest={latestFor(experiments.data, paper.key)} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function PaperRow({ paper, latest }: { paper: (typeof PAPERS)[number]; latest: LabExperiment | null }) {
  const results = useResults(latest?.id ?? null);
  const verdicts = results.data?.verdicts ?? [];
  const supported = verdicts.filter((v) => v.verdict === "supported").length;
  return (
    <Link href={`/research/${paper.key}`} className="group flex items-center gap-4 rounded-2xl border bg-card p-5 shadow-xs transition-colors hover:border-foreground/20 focus-visible:outline-2 focus-visible:outline-ring">
      <div className="min-w-0 flex-1">
        <div className="text-[17px] font-semibold tracking-tight">{paper.label}</div>
        <div className="mt-1 text-[15px] text-muted-foreground">{paper.question}</div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        {!latest && <StatusChip tone="neutral">No run yet</StatusChip>}
        {latest && latest.status === "invalid_run" && <VerdictChip verdict="invalid_run" />}
        {latest && latest.status !== "invalid_run" && verdicts.length > 0 && (
          <StatusChip tone={supported === verdicts.length ? "ok" : "warn"}>{supported} of {verdicts.length} supported</StatusChip>
        )}
        <span className="text-xs text-muted-foreground">{latest ? "Lab" : "Sample only"}</span>
      </div>
      <ChevronRight className="size-4 text-muted-foreground group-hover:text-foreground" aria-hidden />
    </Link>
  );
}
