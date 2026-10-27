"use client";

// Numbers from outside the Lab for one paper: figures published in a paper's tables, and the Lab's own runs of a public
// benchmark. On the chart they are dashed lines; here each one says where it comes from, so nobody mistakes one for the other.
import { ExternalLink } from "lucide-react";
import type { LabReference, ResearchPaper } from "@/contracts/research";
import { Folded } from "@/components/brain/card-pager";
import { StatusChip } from "@/components/brain/primitives";
import { useReferences } from "./lab-api";
import { percent } from "./lab-ui";

/** A short chart label: the benchmark and what the figure measures ("PhantomPolicy: No enforcement"). */
export const referenceLabel = (r: LabReference) => `${r.benchmark}: ${(r.note ?? r.model).split(",")[0]}`;

/** One dashed line per kind of figure: the first row of each label (rows come largest first), so lines never stack. */
export const chartLines = (rows: LabReference[]) => rows.filter((r, i) => rows.findIndex((o) => referenceLabel(o) === referenceLabel(r)) === i);

export function References({ paper }: { paper: ResearchPaper }) {
  const references = useReferences(paper);
  const rows = references.data ?? [];
  if (rows.length === 0) return null;  // nothing outside the Lab for this paper yet, so nothing to show
  const groups = [...new Set(rows.map((r) => r.benchmark))];
  return (
    <Folded title="Public benchmarks">
      <div className="space-y-6">
        {groups.map((benchmark) => {
          const inGroup = rows.filter((r) => r.benchmark === benchmark);
          const first = inGroup[0];
          return (
            <div key={benchmark}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[15px] font-medium">{benchmark}</span>
                <StatusChip tone={first.ours ? "ok" : "neutral"}>{first.ours ? "Our run" : first.peerReviewed ? "Peer reviewed" : "Preprint"}</StatusChip>
              </div>
              <ul className="mt-2 divide-y text-[15px]">
                {inGroup.map((r) => (
                  <li key={r.id} className="flex items-baseline justify-between gap-4 py-2">
                    <span>{r.note ?? r.metricKey.replaceAll("_", " ")} <span className="text-[13px] text-muted-foreground">· {r.metricKey.replaceAll("_", " ")} · {r.model}</span></span>
                    <span className="tabular font-semibold">{percent(r.value)}{r.n ? <span className="font-normal text-muted-foreground"> of {r.n}</span> : null}</span>
                  </li>
                ))}
              </ul>
              <a href={first.sourceUrl} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-[13px] text-muted-foreground underline">
                {first.sourceTitle} <ExternalLink className="size-3" aria-hidden />
              </a>
            </div>
          );
        })}
      </div>
    </Folded>
  );
}
