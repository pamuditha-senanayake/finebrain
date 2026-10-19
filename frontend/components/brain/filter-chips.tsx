"use client";

import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

/** What is filtered right now, one chip each, and one button to clear them all. Shows nothing when nothing is applied. */
export function FilterChips({ filters, labels, onRemove, onClear }: { filters: Record<string, string>; labels: Record<string, string>; onRemove: (field: string) => void; onClear: () => void }) {
  const applied = Object.entries(filters);
  if (applied.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Applied filters">
      {applied.map(([field, value]) => (
        <button key={field} type="button" onClick={() => onRemove(field)} aria-label={`Remove filter ${labels[field] ?? field}: ${value}`}
          className="inline-flex h-7 items-center gap-1.5 rounded-full bg-secondary px-3 text-[13px] text-secondary-foreground ring-1 ring-inset ring-foreground/10 transition-colors hover:bg-secondary/70">
          <span className="text-muted-foreground">{labels[field] ?? field}</span> {value.replaceAll("_", " ")} <X className="size-3" aria-hidden />
        </button>
      ))}
      <Button size="xs" variant="ghost" onClick={onClear} className="text-muted-foreground">Clear</Button>
    </div>
  );
}
