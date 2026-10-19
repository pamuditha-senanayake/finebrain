"use client";

import { Crosshair } from "lucide-react";
import Link from "next/link";
import type { AskAnswer } from "@/contracts";
import { Button } from "@/components/ui/button";
import { useUi } from "@/lib/store";

/** One "Show me" under an answer: opens the page the answer came from, with that sentence lit (step 11). Nothing when there is no place to show. */
export function ShowMe({ answer, className }: { answer: AskAnswer; className?: string }) {
  const setAsk = useUi((s) => s.setAskOpen);
  const action = answer.actions?.[0];
  if (!action) return null;
  return (
    <Button asChild size="sm" className={className}>
      <Link href={action.href} onClick={() => setAsk(false)} data-testid="show-me">
        <Crosshair aria-hidden /> {action.label}
      </Link>
    </Button>
  );
}
