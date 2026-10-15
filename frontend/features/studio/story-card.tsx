"use client";

import { ArrowRight, Check, ChevronLeft, ChevronRight, Hammer } from "lucide-react";
import { useState } from "react";
import type { Scenario, Story, StudioItem } from "@/contracts";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** One case as a BDD scenario: Given, When, Then today, and what should happen instead. */
export function ScenarioView({ sc, coverage, onBuild }: { sc: Scenario; coverage?: StudioItem[] | null; onBuild?: () => void }) {
  const rows: [string, string][] = [
    ...sc.given.map((g, i): [string, string] => [i === 0 ? "Given" : "And", g]),
    ["When", sc.when],
    ...sc.then.map((t, i): [string, string] => [i === 0 ? "Then" : "And", t]),
  ];
  const thenFrom = sc.given.length + 1;
  return (
    <div className="rounded-2xl border bg-card">
      <p className="px-6 pt-6 text-xl font-semibold leading-snug tracking-tight">{sc.title}</p>
      <dl className="space-y-3 px-6 py-6 text-base">
        {rows.map(([k, v], i) => (
          <div key={i} className="grid grid-cols-[64px_1fr] gap-3">
            <dt className={cn("text-xs font-semibold uppercase leading-6 tracking-wide", i >= thenFrom ? "text-warn-fg" : "text-muted-foreground")}>{k}</dt>
            <dd className="leading-6">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="flex items-start gap-3 border-t bg-ok/5 px-6 py-5 text-base">
        <ArrowRight className="mt-1 size-4 shrink-0 text-ok" aria-hidden />
        <p className="leading-6">{sc.goal}</p>
      </div>
      {coverage !== undefined && (
        <div className="flex min-h-14 items-center gap-2 border-t px-6 py-3 text-sm">
          {coverage && coverage.length > 0 ? (
            <span className="inline-flex items-center gap-2 text-muted-foreground"><Check className="size-4 text-ok" aria-hidden />{coverage.map((p) => p.name).join(", ")}</span>
          ) : (
            <>
              <span className="text-muted-foreground">Not built yet</span>
              {onBuild && <Button size="sm" variant="outline" className="ml-auto" onClick={onBuild}><Hammer /> Build</Button>}
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
    <div className="rounded-xl border bg-surface p-5">
      <p className="text-[15px] font-medium leading-snug">{story.problem}</p>
      <ol className="mt-4 space-y-2.5">
        {story.scenarios.map((sc, i) => (
          <li key={sc.id} className="flex items-center gap-3 text-sm">
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-medium tabular-nums">{i + 1}</span>
            <span>{sc.title}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/**
 * The problem, then its cases as slides: one case on screen at a time, with Back and Next.
 * A long list of Given/When/Then is hard to read, so the person walks through the cases instead.
 */
export function StoryView({ story, coverageFor, onBuild, live }: { story: Story; coverageFor?: (sc: Scenario) => StudioItem[]; onBuild?: (sc: Scenario) => void; live?: boolean }) {
  const n = story.scenarios.length;
  const [at, setAt] = useState(0);
  // When the chat adds a case, show it. Adjusting state while rendering avoids a flash of the old slide.
  const [seen, setSeen] = useState(n);
  if (n !== seen) {
    setSeen(n);
    setAt(n > seen ? n - 1 : Math.min(at, Math.max(0, n - 1)));
  }
  const i = Math.min(at, Math.max(0, n - 1));
  const sc = story.scenarios[i];
  const [today, setToday] = useState(false);

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-surface p-6">
        <p className="text-lg font-medium leading-snug">{story.problem}</p>
        <button type="button" className="mt-3 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline" onClick={() => setToday(!today)} aria-expanded={today}>
          {today ? "Hide how it works today" : "How it works today"}
        </button>
        {today && <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{story.today}</p>}
      </div>

      {sc && (
        <section aria-label="Cases" aria-roledescription="carousel" className="space-y-4">
          <div className="flex items-center gap-3">
            <p className="text-sm font-medium">Case {i + 1} <span className="text-muted-foreground">of {n}</span></p>
            <div className="flex" role="tablist" aria-label="Pick a case">
              {story.scenarios.map((x, j) => (
                // The button is a full 24px target; only the dot inside it shows.
                <button key={x.id} type="button" role="tab" aria-selected={j === i} aria-label={`Case ${j + 1}: ${x.title}`} onClick={() => setAt(j)} className="group grid h-6 min-w-6 place-items-center px-0.5">
                  <span className={cn("block h-1.5 rounded-full transition-all", j === i ? "w-6 bg-primary" : "w-1.5 bg-muted-foreground/40 group-hover:bg-muted-foreground")} />
                </button>
              ))}
            </div>
            <div className="ml-auto flex gap-2">
              <Button size="icon-sm" variant="outline" disabled={i === 0} onClick={() => setAt(i - 1)} aria-label="Previous case"><ChevronLeft /></Button>
              <Button size="icon-sm" variant="outline" disabled={i === n - 1} onClick={() => setAt(i + 1)} aria-label="Next case"><ChevronRight /></Button>
            </div>
          </div>
          <div key={sc.id} className={cn("animate-in fade-in slide-in-from-right-2 duration-300", live && "rounded-2xl ring-2 ring-primary/20")} role="group" aria-roledescription="slide" aria-label={`Case ${i + 1} of ${n}`}>
            <ScenarioView sc={sc} coverage={coverageFor ? coverageFor(sc) : undefined} onBuild={onBuild ? () => onBuild(sc) : undefined} />
          </div>
        </section>
      )}
    </div>
  );
}
