"use client";

// Small pieces every Research screen shares: the papers, verdict chips, a numbered step line, and the gate that explains
// why the Lab cannot answer here instead of showing an error.
import { Check, FlaskConical } from "lucide-react";
import type { ReactNode } from "react";
import type { ResearchPaper } from "@/contracts/research";
import { EmptyState, LoadingState, StatusChip, type Tone } from "@/components/brain/primitives";
import { cn } from "@/lib/utils";
import { useLabStatus } from "./lab-api";

export const PAPERS: { key: ResearchPaper; label: string; question: string }[] = [
  { key: "policies", label: "Freshness", question: "Do answers stay current when policy changes?" },
  { key: "skills", label: "Skills", question: "Does a skill match how the work is really done?" },
  { key: "security", label: "Security", question: "Does enforcement at the call stop forbidden actions?" },
  { key: "integration", label: "Integration", question: "Does the whole brain beat retrieval alone?" },
];

/** What one case of a paper's run is called: a graded answer, or an agent's episode. */
export const caseWord = (paper: string | undefined, plural = true) => (paper === "policies" || !paper ? (plural ? "answers" : "question") : (plural ? "episodes" : "episode"));

export const paperLabel = (key: string) => PAPERS.find((p) => p.key === key)?.label ?? key;

const VERDICT: Record<string, [Tone, string]> = {
  supported: ["ok", "Supported"],
  not_supported: ["warn", "Not supported"],
  invalid_run: ["risk", "Invalid run"],
};

export function VerdictChip({ verdict }: { verdict: string }) {
  const [tone, words] = VERDICT[verdict] ?? ["neutral", verdict.replaceAll("_", " ")];
  return <StatusChip tone={tone}>{words}</StatusChip>;
}

export const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
export const points = (value: number) => `${value >= 0 ? "+" : "−"}${Math.abs(value * 100).toFixed(1)} pts`;

/** Done, current and upcoming steps. They are not buttons, so they do not look like buttons. */
export function StepLine({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className="mb-8 flex flex-wrap items-center gap-x-6 gap-y-2" aria-label="Steps">
      {steps.map((step, i) => (
        <li key={step} className="flex items-center gap-2 text-[15px]" aria-current={i === current ? "step" : undefined}>
          <span className={cn("grid size-6 place-items-center rounded-full text-xs font-semibold",
            i < current ? "bg-ok/15 text-ok" : i === current ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>
            {i < current ? <Check className="size-3.5" aria-label="done" /> : i + 1}
          </span>
          <span className={cn(i === current ? "font-medium" : "text-muted-foreground")}>{step}</span>
        </li>
      ))}
    </ol>
  );
}

/** The Lab's children, or a plain explanation of why the Lab cannot run here and what to do about it. */
export function LabGate({ children }: { children: ReactNode }) {
  const status = useLabStatus();
  if (status.isLoading) return <LoadingState rows={3} label="Checking the Lab" />;
  if (status.error) {
    return <EmptyState title="The Lab is not available here" description={(status.error as Error).message} action={<FlaskConical className="mx-auto size-5 text-muted-foreground" aria-hidden />} />;
  }
  if (status.data?.store !== "ready") return <EmptyState title="The Lab's store does not answer" description="Postgres is down. Start the infrastructure, then reload." />;
  return <>{children}</>;
}
