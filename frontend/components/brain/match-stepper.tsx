"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

/** "3 of 23" with Back and Next: one match at a time. Nothing shows until a search has matches. */
export function MatchStepper({ count, index, onStep, searched }: { count: number; index: number; onStep: (next: number) => void; searched: boolean }) {
  if (!searched) return null;
  if (count === 0) return <span className="text-[13px] text-muted-foreground">No match</span>;
  return (
    <div className="flex items-center gap-1" role="group" aria-label="Matches">
      <Button size="icon-sm" variant="ghost" aria-label="Previous match" onClick={() => onStep((index - 1 + count) % count)}>
        <ChevronLeft />
      </Button>
      <span className="min-w-16 text-center text-[13px] tabular-nums" aria-live="polite" data-testid="match-count">
        {index + 1} of {count.toLocaleString()}
      </span>
      <Button size="icon-sm" variant="ghost" aria-label="Next match" onClick={() => onStep((index + 1) % count)}>
        <ChevronRight />
      </Button>
    </div>
  );
}
