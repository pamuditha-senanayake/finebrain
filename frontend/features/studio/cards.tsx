"use client";

import { AlarmClock, BookOpen, Bot, ClipboardList, GraduationCap, Radar, Repeat, Workflow, Wrench, type LucideIcon } from "lucide-react";
import type { StudioCard, StudioKind } from "@/contracts";
import { StatusChip, statusTone } from "@/components/brain/primitives";
import { relTime } from "@/lib/format";
import { KIND_COLOR } from "@/lib/studio/graph";
import { KIND_LABEL } from "@/lib/studio/spec";
import { cn } from "@/lib/utils";

export const KIND_ICON: Record<StudioKind, LucideIcon> = {
  workflow: Workflow,
  sensor: Radar,
  scheduler: AlarmClock,
  agent: Bot,
  skill: GraduationCap,
  policy: BookOpen,
  tool: Wrench,
  template: ClipboardList,
  loop: Repeat,
};

export function kindColor(kind: StudioKind) {
  return kind === "workflow" ? "var(--primary)" : KIND_COLOR[kind];
}

export function KindIcon({ kind, className }: { kind: StudioKind; className?: string }) {
  const Icon = KIND_ICON[kind];
  return <Icon className={cn("size-3.5 shrink-0", className)} style={{ color: kindColor(kind) }} aria-label={KIND_LABEL[kind]} />;
}

/** A top match in a chat reply: an item, or one version of it. Picking it opens it in the details panel. */
export function MatchCard({ card, now, onOpen }: { card: StudioCard; now: number; onOpen: (c: StudioCard) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(card)}
      className={cn("group flex min-w-0 flex-col gap-1 rounded-xl border bg-card p-2.5 text-left text-xs shadow-xs transition-colors hover:border-primary/40 hover:bg-accent/40", card.current && "border-primary/30")}
      style={{ borderTop: `3px solid ${kindColor(card.kind)}` }}
    >
      <span className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        <KindIcon kind={card.kind} className="size-3" />
        <span className="truncate">{card.subtitle}</span>
      </span>
      <span className="line-clamp-1 text-[13px] font-medium text-foreground">{card.title}</span>
      <span className="line-clamp-3 text-muted-foreground">{card.body}</span>
      <span className="mt-auto flex flex-wrap items-center gap-1 pt-1">
        {card.badges.slice(0, 3).map((b) => (
          <StatusChip key={b} tone={statusTone(b === "minimal" ? "ok" : b === "moderate" ? "pending" : b === "breaking" ? "failed" : b)} className="h-4 px-1.5 text-[10px]">
            {b}
          </StatusChip>
        ))}
        {card.at && <span className="ml-auto text-[10px] text-muted-foreground">{relTime(card.at, now)}</span>}
      </span>
    </button>
  );
}
