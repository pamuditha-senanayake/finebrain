"use client";

// One run, live: answers done, money spent against the cap, and why it stopped if it did. When it finishes, the way to its
// verdict. A run that failed or was stopped can be resumed; it continues after the last answer it stored.
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { EmptyState, PageHeader, QueryView, Section, Status } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useExperiment, useProgress, useStartExperiment } from "./lab-api";
import { LabGate, caseWord, paperLabel } from "./lab-ui";

const LIVE = new Set(["running", "estimated", "draft"]);
const STOPPED_WORDS: Record<string, string> = {
  budget_reached: "Stopped at the cost cap. The answers so far are kept and marked incomplete.",
  failed: "Stopped by an error. Resume continues after the last stored answer.",
  invalid_run: "Finished, but a gate failed, so no verdict can be read.",
};

export function LabRun() {
  const id = useParams<{ id: string }>().id;
  const experiment = useExperiment(id);
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader eyebrow={<Link href="/research/lab" className="inline-flex items-center gap-1 hover:text-foreground"><ArrowLeft className="size-3" /> Lab</Link>}
        title={experiment.data ? `${paperLabel(experiment.data.paper)} run` : "Run"} />
      <LabGate>
        <QueryView query={experiment} empty={<EmptyState title="No such run" />}>
          {(e) => <Live id={id} paper={e.paper} conditions={e.conditions} />}
        </QueryView>
      </LabGate>
    </div>
  );
}

function Live({ id, paper, conditions }: { id: string; paper: string; conditions: string[] }) {
  const progress = useProgress(id, true);
  const start = useStartExperiment();
  return (
    <QueryView query={progress}>
      {(p) => {
        const live = LIVE.has(p.status) && !p.stalled;
        const resumable = p.status === "failed" || p.stalled;
        const share = p.total ? Math.round((p.done / p.total) * 100) : 0;
        return (
          <Section title={<span className="inline-flex items-center gap-2">Progress <Status value={p.status} /></span>} description={`Conditions ${conditions.join(", ")}`}>
            <div aria-live="polite" className="space-y-4">
              <div>
                <div className="mb-2 flex justify-between text-[15px]"><span className="capitalize">{caseWord(paper)}</span><span className="tabular">{p.done} of {p.total}</span></div>
                <Progress value={share} aria-label={`${caseWord(paper)} done`} />
              </div>
              <div className="flex justify-between text-[15px]"><span>Spent</span><span className="tabular">${p.costUsd.toFixed(4)} of ${p.budgetUsd}</span></div>
              {p.stalled && <p className="text-[15px]">The worker stopped, for example when the server restarted. Resume continues after the last stored answer.</p>}
              {STOPPED_WORDS[p.status] && <p className="text-[15px]">{STOPPED_WORDS[p.status]}</p>}
              {p.error && <p role="alert" className="break-words text-[13px] text-risk">{p.error}</p>}
            </div>
            <div className="mt-6 flex justify-end gap-2">
              {(resumable || p.status === "estimated") && (
                <Button disabled={start.isPending} onClick={() => start.mutate(id)}>{resumable ? "Resume" : "Start run"}</Button>
              )}
              {!live && !resumable && <Button asChild><Link href={`/research/${paper}?experiment=${id}`}>See the verdict</Link></Button>}
            </div>
          </Section>
        );
      }}
    </QueryView>
  );
}
