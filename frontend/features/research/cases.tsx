"use client";

// The cases of a run, one at a time with Back and Next: the question, what the gold answer is, what the model said, and
// how the rule graded it. Filters: one condition, or failed answers only.
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { KeyValue, QueryView, StatusChip, type Tone } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { useCase } from "./lab-api";

const LABEL_TONE: Record<string, Tone> = { fresh: "ok", stale: "risk", mixed: "warn", refused: "neutral", wrong: "risk" };

export function CaseViewer({ experimentId, conditions, labels }: { experimentId: string; conditions: string[]; labels: Record<string, string> }) {
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
          <Label htmlFor="failed-only" className="text-[13px]">Not fresh only</Label>
        </div>
      </div>
      <QueryView query={page} isEmpty={(p) => p.total === 0} rows={3}>
        {(p) => {
          const shown = p.items[0];
          const outcome = shown.outcome;
          return (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-[15px] text-muted-foreground">{at + 1} of {p.total}</span>
                <div className="flex gap-2">
                  <Button size="icon-sm" variant="outline" disabled={at === 0} onClick={() => setAt(at - 1)} aria-label="Back"><ChevronLeft /></Button>
                  <Button size="icon-sm" variant="outline" disabled={at >= p.total - 1} onClick={() => setAt(at + 1)} aria-label="Next"><ChevronRight /></Button>
                </div>
              </div>
              <div className="rounded-xl border p-5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[13px] text-muted-foreground">{shown.caseId} · {labels[shown.condition] ?? shown.condition} · seed {shown.seed}</span>
                  <StatusChip tone={LABEL_TONE[outcome.label] ?? "neutral"}>{outcome.label}</StatusChip>
                </div>
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
            </div>
          );
        }}
      </QueryView>
    </div>
  );
}
