"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

/** One card at a time, with "2 of 7", Back and Next (the house rule for lists of rich items). startAt picks the first card shown. */
export function CardPager<T>({ items, getId, render, label, startAt, testId }: {
  items: T[];
  getId: (item: T) => string;
  render: (item: T) => ReactNode;
  label: string;
  startAt?: string | null;
  testId?: string;
}) {
  const [at, setAt] = useState(() => Math.max(0, items.findIndex((item) => getId(item) === startAt)));
  const n = items.length;
  const i = Math.min(at, n - 1);
  return (
    <section className="mx-auto max-w-2xl space-y-4" aria-label={label} data-testid={testId}>
      <div className="flex items-center justify-between">
        <span className="text-[15px] text-muted-foreground">{i + 1} of {n}</span>
        <div className="flex gap-2">
          <Button size="icon-sm" variant="outline" disabled={i === 0} onClick={() => setAt(i - 1)} aria-label="Back"><ChevronLeft /></Button>
          <Button size="icon-sm" variant="outline" disabled={i === n - 1} onClick={() => setAt(i + 1)} aria-label="Next"><ChevronRight /></Button>
        </div>
      </div>
      <div key={getId(items[i])} className="animate-in fade-in slide-in-from-right-2 duration-300" role="group" aria-roledescription="slide" aria-label={`${label}: ${i + 1} of ${n}`}>
        {render(items[i])}
      </div>
    </section>
  );
}

/** The quiet place for finished or secondary things: folded away until someone opens it. */
export function Folded({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="group mx-auto max-w-2xl pt-6">
      <summary className="cursor-pointer list-none text-[15px] font-medium text-muted-foreground hover:text-foreground">
        <ChevronRight className="mr-1 inline size-4 transition-transform group-open:rotate-90" aria-hidden />
        {title}
      </summary>
      <div className="mt-4">{children}</div>
    </details>
  );
}
