"use client";

// The cases of a run, one at a time with Back and Next. A freshness case: the question, the gold answer, what the model said,
// and how the rule graded it. A security episode: what the agent did, what the access check refused, and whether anything
// restricted reached it. Filters: one condition, or failed cases only.
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import type { FreshnessOutcome, LabCase, SecurityOutcome } from "@/contracts/research";
import { KeyValue, QueryView, StatusChip, type Tone } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useCase } from "./lab-api";

const LABEL_TONE: Record<string, Tone> = { fresh: "ok", stale: "risk", mixed: "warn", refused: "neutral", wrong: "risk" };
const EPISODE: Record<string, [Tone, string]> = { leak: ["risk", "Leaked"], met: ["ok", "Goal met"], held: ["neutral", "Held"] };
const TOOL_WORDS: Record<string, string> = { issue_refund: "Refund", reply_customer: "Reply", "refund.propose": "Refund", "reply.draft": "Reply" };

const isSecurity = (outcome: LabCase["outcome"]): outcome is SecurityOutcome => "path" in outcome;
const listed = (values: string[], none: string) => (values.length ? values.map((v) => TOOL_WORDS[v] ?? v).join(", ") : none);

export function CaseViewer({ experimentId, conditions, labels, failedLabel = "Not fresh only" }: { experimentId: string; conditions: string[]; labels: Record<string, string>; failedLabel?: string }) {
  const [condition, setCondition] = useState<string | null>(null);
  const [failedOnly, setFailedOnly] = useState(false);
  const [at, setAt] = useState(0);
  const page = useCase(experimentId, condition, failedOnly, at);
  const choose = (code: string | null) => { setCondition(code); setAt(0); };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Condition">
        {[null, ...conditions].map((code) => (
          <button key={code ?? "all"} type="button" onClick={() => choose(code)} aria-pressed={condition === code}
            className={cn("rounded-full border px-3 py-1 text-[13px]", condition === code ? "border-foreground bg-foreground text-background" : "hover:border-foreground/40")}>
            {code ? labels[code] ?? code : "All"}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <Switch id="failed-only" checked={failedOnly} onCheckedChange={(on) => { setFailedOnly(on); setAt(0); }} />
          <Label htmlFor="failed-only" className="text-[13px]">{failedLabel}</Label>
        </div>
      </div>
      <QueryView query={page} isEmpty={(p) => p.total === 0} rows={3}>
        {(p) => {
          const shown = p.items[0];
          return (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-[15px] text-muted-foreground">{at + 1} of {p.total}</span>
                <div className="flex gap-2">
                  <Button size="icon-sm" variant="outline" disabled={at === 0} onClick={() => setAt(at - 1)} aria-label="Back"><ChevronLeft /></Button>
                  <Button size="icon-sm" variant="outline" disabled={at >= p.total - 1} onClick={() => setAt(at + 1)} aria-label="Next"><ChevronRight /></Button>
                </div>
              </div>
              {isSecurity(shown.outcome)
                ? <EpisodeCard shown={shown} outcome={shown.outcome} labels={labels} />
                : <AnswerCard shown={shown} outcome={shown.outcome} labels={labels} />}
            </div>
          );
        }}
      </QueryView>
    </div>
  );
}

function CardHead({ shown, labels, chip }: { shown: LabCase; labels: Record<string, string>; chip: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[13px] text-muted-foreground">{shown.caseId} · {labels[shown.condition] ?? shown.condition} · seed {shown.seed}</span>
      {chip}
    </div>
  );
}

function AnswerCard({ shown, outcome, labels }: { shown: LabCase; outcome: FreshnessOutcome; labels: Record<string, string> }) {
  return (
    <div className="rounded-xl border p-5">
      <CardHead shown={shown} labels={labels} chip={<StatusChip tone={LABEL_TONE[outcome.label] ?? "neutral"}>{outcome.label}</StatusChip>} />
      {outcome.question && <p className="mt-3 text-[15px] text-muted-foreground">{outcome.question}</p>}
      <p className="mt-2 text-[15px] font-medium">“{outcome.answer || "No answer"}”</p>
      <KeyValue className="mt-4 text-[15px]" items={[
        ["Gold", outcome.expected],
        ["Old value", outcome.superseded.join(", ") || "none"],
        ["Question kind", outcome.kind.replaceAll("_", " ")],
        ["Evidence reached", (outcome.either_hit ?? outcome.eitherHit) ? "yes" : "no"],
        ["Retrieved", `${outcome.items.length} passages`],
      ]} />
    </div>
  );
}

function EpisodeCard({ shown, outcome, labels }: { shown: LabCase; outcome: SecurityOutcome; labels: Record<string, string> }) {
  const [tone, words] = EPISODE[outcome.label] ?? ["neutral", outcome.label];
  const kind = outcome.benign ? "Benign work" : outcome.attack ? "Attack" : "Forbidden read";
  return (
    <div className="rounded-xl border p-5">
      <CardHead shown={shown} labels={labels} chip={<StatusChip tone={tone}>{words}</StatusChip>} />
      <p className="mt-3 text-[15px] font-medium">{kind} · {outcome.path === "act" ? "an agent run" : "a question through Ask"}</p>
      <KeyValue className="mt-4 text-[15px]" items={[
        ["Did", outcome.path === "act" ? listed(outcome.done, "nothing outside") : "answered"],
        ["Refused at the call", listed(outcome.denied, "nothing")],
        ["Restricted reached", listed(outcome.leaked, "none")],
        ["Run ended", outcome.outcome?.replaceAll("_", " ") ?? "not a run"],
      ]} />
      {outcome.said && (
        <details className="mt-4 text-[13px]">
          <summary className="cursor-pointer text-muted-foreground">What it said</summary>
          <p className="mt-2 whitespace-pre-wrap break-words">{outcome.said}</p>
        </details>
      )}
    </div>
  );
}
