"use client";

import { ArrowRight, Check, Hammer } from "lucide-react";
import type { Scenario, Story, StudioItem } from "@/contracts";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** One case as a BDD scenario: Given, When, Then today, and what should happen instead. */
export function ScenarioView({ sc, index, coverage, onBuild, animate }: { sc: Scenario; index: number; coverage?: StudioItem[] | null; onBuild?: () => void; animate?: boolean }) {
  const rows: [string, string][] = [
    ...sc.given.map((g, i): [string, string] => [i === 0 ? "Given" : "And", g]),
    ["When", sc.when],
    ...sc.then.map((t, i): [string, string] => [i === 0 ? "Then" : "And", t]),
  ];
  return (
    <div className={cn("rounded-xl border bg-card", animate && "animate-in fade-in slide-in-from-bottom-1 fill-mode-both duration-500")} style={animate ? { animationDelay: `${index * 140}ms` } : undefined}>
      <div className="flex items-center gap-3 px-4 pt-4">
        <span className="grid size-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-medium tabular-nums">{index + 1}</span>
        <p className="min-w-0 flex-1 text-[15px] font-medium leading-snug">{sc.title}</p>
      </div>
      <dl className="space-y-1.5 px-4 py-3 text-sm">
        {rows.map(([k, v], i) => (
          <div key={i} className="grid grid-cols-[52px_1fr] gap-2">
            <dt className={cn("text-xs font-semibold uppercase leading-5 tracking-wide", k === "Then" || (k === "And" && i > sc.given.length) ? "text-warn-fg" : "text-muted-foreground")}>{k}</dt>
            <dd className="leading-5">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="flex items-start gap-2 border-t bg-ok/5 px-4 py-3 text-sm">
        <ArrowRight className="mt-0.5 size-4 shrink-0 text-ok" aria-hidden />
        <p className="leading-5"><span className="font-medium">Instead: </span>{sc.goal}</p>
      </div>
      {coverage !== undefined && (
        <div className="flex items-center gap-2 border-t px-4 py-2.5 text-xs">
          {coverage && coverage.length > 0 ? (
            <span className="inline-flex items-center gap-1.5 text-muted-foreground"><Check className="size-3.5 text-ok" aria-hidden />Handled by {coverage.map((p) => p.name).join(", ")}</span>
          ) : (
            <>
              <span className="text-muted-foreground">Not built yet</span>
              {onBuild && <Button size="xs" variant="outline" className="ml-auto" onClick={onBuild}><Hammer /> Build this case</Button>}
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** Short form for the chat: the problem and the case titles. The parts pane shows each case in full. */
export function StorySummary({ story }: { story: Story }) {
  return (
    <div className="rounded-xl border bg-surface p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Problem</p>
      <p className="mt-1.5 text-[15px] font-medium leading-snug">{story.problem}</p>
      <ol className="mt-4 space-y-2">
        {story.scenarios.map((sc, i) => (
          <li key={sc.id} className="flex items-center gap-3 text-sm">
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-medium tabular-nums">{i + 1}</span>
            <span>{sc.title}</span>
          </li>
        ))}
      </ol>
      <p className="mt-4 text-xs text-muted-foreground">Each case is written out on the right.</p>
    </div>
  );
}

/** The problem, how it is handled today, and its cases. Used in the chat (to confirm) and in the parts pane. */
export function StoryView({ story, coverageFor, onBuild, animate, compact }: { story: Story; coverageFor?: (sc: Scenario) => StudioItem[]; onBuild?: (sc: Scenario) => void; animate?: boolean; compact?: boolean }) {
  return (
    <div className="space-y-4">
      <div className={cn("rounded-xl border bg-surface", compact ? "p-4" : "p-5")}>
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Problem</p>
        <p className={cn("mt-1.5 font-medium leading-snug", compact ? "text-[15px]" : "text-lg")}>{story.problem}</p>
        <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Today</p>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{story.today}</p>
      </div>
      <div className="space-y-3">
        {story.scenarios.map((sc, i) => (
          <ScenarioView key={sc.id} sc={sc} index={i} animate={animate} coverage={coverageFor ? coverageFor(sc) : undefined} onBuild={onBuild ? () => onBuild(sc) : undefined} />
        ))}
      </div>
    </div>
  );
}
