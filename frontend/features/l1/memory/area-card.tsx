"use client";

// area-card.tsx: one brain area at a time: its work this week, its patterns against the budget, its skills, and
// the three kinds of drift. Drift opens as cards, one at a time, each with its draft fix, where it stands, and the traces.
// Used by: memory.tsx. Uses: areas.ts, components/brain (CardPager, Folded), lib/api/hooks.
import { Check, ChevronLeft, ChevronRight, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { AreaKey, DriftItem, DriftKind, DriftState, MemoryArea } from "@/contracts";
import { CardPager, Folded } from "@/components/brain/card-pager";
import { QueryView } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { useMemoryArea } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";
import { AREA_COLOR, AREA_ORDER } from "./areas";

// Config
const KIND_LABEL: Record<DriftKind, string> = { skill: "Skill drift", policy: "Policy drift", security: "Security drift" };
const KIND_QUESTION: Record<DriftKind, string> = { skill: "Still followed?", policy: "Still how we work?", security: "Right access?" };
// Docs/CB_Living_Memory_Architecture.md section 8b: an L1 user approves every fix, then a 14-day re-check.
const STATE_STEPS: { key: DriftState; label: string }[] = [
  { key: "detected", label: "Detected" }, { key: "sent_to_l1", label: "Sent to L1" }, { key: "awaiting_approval", label: "Waiting" },
  { key: "approved", label: "Approved" }, { key: "resolved", label: "Resolved" },
];
const RECHECK_WORDS = { watching: "watching", dropped: "drift dropped", still_drifting: "still drifting" };

export function AreaCard({ areaKey, onClose, onPick }: { areaKey: AreaKey; onClose: () => void; onPick: (key: AreaKey) => void }) {
  const detail = useMemoryArea(areaKey);
  const at = AREA_ORDER.indexOf(areaKey);
  return (
    <section className="space-y-4" aria-label="Area" data-testid="area-card">
      <div className="flex items-center justify-between">
        <span className="text-[15px] text-muted-foreground">{at + 1} of {AREA_ORDER.length}</span>
        <div className="flex gap-2">
          <Button size="icon-sm" variant="outline" disabled={at === 0} onClick={() => onPick(AREA_ORDER[at - 1])} aria-label="Previous area"><ChevronLeft /></Button>
          <Button size="icon-sm" variant="outline" disabled={at === AREA_ORDER.length - 1} onClick={() => onPick(AREA_ORDER[at + 1])} aria-label="Next area"><ChevronRight /></Button>
          <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close area"><X /></Button>
        </div>
      </div>
      <QueryView query={detail} rows={5}>
        {(d) => <Card key={areaKey} area={d.area} drifts={d.drifts} patterns={d.patterns.slice(0, 5)} />}
      </QueryView>
    </section>
  );
}

function Card({ area, drifts, patterns }: { area: MemoryArea; drifts: DriftItem[]; patterns: { id: string; name: string; share: number }[] }) {
  const [showDrift, setShowDrift] = useState(false);
  const quiet = area.traces7d === 0;
  return (
    <div className="space-y-7 rounded-2xl border bg-card/95 p-7 shadow-sm backdrop-blur animate-in fade-in duration-300">
      <h2 className="flex items-center gap-3 text-xl font-semibold">
        <span className="size-3 rounded-full" style={{ background: AREA_COLOR[area.key] }} aria-hidden />
        {area.name}
      </h2>
      {quiet ? <p className="text-[15px] text-muted-foreground">Quiet this week.</p> : (
        <dl className="grid grid-cols-3 gap-4">
          <Figure label="Traces" value={area.traces7d.toLocaleString()} hint="this week" />
          <Figure label="Patterns" value={`${area.patterns}`} hint={`of ${area.patternBudget}`} />
          <Figure label="Skills" value={`${area.skills.authored + area.skills.fromTraces}`} hint={area.skills.fromTraces ? `${area.skills.fromTraces} from traces` : "written"} />
        </dl>
      )}
      <ul className="space-y-3" aria-label="Drift">
        {(["skill", "policy", "security"] as const).map((kind) => <DriftLine key={kind} kind={kind} count={area.drift[kind]} />)}
      </ul>
      <div className="flex flex-wrap gap-3">
        <Button asChild variant="outline"><Link href={`/l1/memory/traces?area=${area.key}`}>See traces</Link></Button>
        {drifts.length > 0 && <Button onClick={() => setShowDrift((v) => !v)}>{showDrift ? "Hide drift" : `See drift (${drifts.length})`}</Button>}
      </div>
      {showDrift && <CardPager items={drifts} getId={(x) => x.id} label="Drift" testId="drift-pager" render={(x) => <DriftCard drift={x} />} />}
      {patterns.length > 0 && (
        <Folded title="Top patterns">
          <ul className="space-y-2">
            {patterns.map((p) => (
              <li key={p.id} className="flex items-baseline justify-between gap-4 text-[15px]">
                <span className="truncate">{p.name}</span>
                <span className="tabular-nums text-muted-foreground">{Math.round(p.share * 100)}%</span>
              </li>
            ))}
          </ul>
        </Folded>
      )}
    </div>
  );
}

function Figure({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div>
      <dt className="text-[12px] font-medium uppercase tracking-[0.07em] text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
      <dd className="text-[13px] text-muted-foreground">{hint}</dd>
    </div>
  );
}

// "No drift" is plain grey text; only drift gets the accent, with a count, so colour is never the only signal.
function DriftLine({ kind, count }: { kind: DriftKind; count: number }) {
  return (
    <li className="flex items-center justify-between gap-4 text-[15px]">
      <span>{KIND_LABEL[kind]} <span className="text-muted-foreground">· {KIND_QUESTION[kind]}</span></span>
      {count > 0
        ? <span className="rounded-full bg-primary/12 px-2.5 py-0.5 text-[13px] font-semibold text-primary">{count} drifting</span>
        : <span className="text-[13px] text-muted-foreground">No drift</span>}
    </li>
  );
}

function DriftCard({ drift }: { drift: DriftItem }) {
  const asShare = drift.metric.usual <= 1 && drift.metric.latest <= 1 && drift.kind === "skill";
  const show = (n: number) => (asShare ? `${Math.round(n * 100)}%` : String(n));
  return (
    <div className="space-y-5 rounded-2xl border p-6">
      <div className="space-y-1">
        <p className="text-[13px] font-medium uppercase tracking-[0.07em] text-primary">{KIND_LABEL[drift.kind]}</p>
        <h3 className="text-lg font-semibold">{drift.subject.name}</h3>
        <p className="text-[15px] text-muted-foreground">{drift.summary}</p>
      </div>
      <div className="flex items-baseline gap-3">
        <span className="text-[15px] text-muted-foreground">{show(drift.metric.usual)}</span>
        <span aria-hidden className="text-muted-foreground">→</span>
        <span className="text-3xl font-semibold tabular-nums text-primary">{show(drift.metric.latest)}</span>
        <span className="text-[13px] text-muted-foreground">{drift.metric.label.toLowerCase()}</span>
      </div>
      <p className="text-[15px]">
        {fixWords(drift)}
      </p>
      <StateSteps state={drift.state} />
      {drift.reopenedNote && <p className="text-[13px] text-primary">Reopened: {drift.reopenedNote}</p>}
      {drift.recheck && <p className="text-[13px] text-muted-foreground">Re-check until {drift.recheck.until.slice(0, 10)}: {RECHECK_WORDS[drift.recheck.result]}</p>}
      <div className="flex flex-wrap gap-3">
        <Button asChild variant="outline"><Link href={`/l1/memory/traces?area=${drift.area}&flag=drift`}>See drifting traces</Link></Button>
        {drift.fix?.changeRequestId
          ? <Button asChild variant="ghost"><Link href={`/l2/versioning/${drift.fix.changeRequestId}`}>Open the change request</Link></Button>
          : <Button asChild variant="ghost"><Link href="/l1/digest">Open To review</Link></Button>}
      </div>
    </div>
  );
}

// A fix is a draft only while it is being drafted or has a change request; past that without one, an L1 user decides.
function fixWords(drift: DriftItem) {
  if (!drift.fix) return <span className="text-muted-foreground">No draft: access drift goes straight to an L1 user.</span>;
  if (drift.fix.changeRequestId || drift.state === "detected") return <>Draft fix: {drift.fix.summary}</>;
  return <>Suggested: {drift.fix.summary} <span className="text-muted-foreground">No change could be opened, so an L1 user decides.</span></>;
}

// Where the drift stands, as a numbered step line: done, now (accent ring), and still to come. Text, never buttons.
function StateSteps({ state }: { state: DriftState }) {
  const now = STATE_STEPS.findIndex((s) => s.key === state);
  return (
    <ol className="grid grid-cols-5 gap-1" aria-label={`Status: ${STATE_STEPS[now].label}`}>
      {STATE_STEPS.map((step, i) => (
        <li key={step.key} className="flex flex-col items-center gap-1.5 text-center" aria-current={i === now ? "step" : undefined}>
          <span className={cn("flex size-7 items-center justify-center rounded-full border text-[12px] font-semibold tabular-nums",
            i < now && "border-foreground/30 bg-foreground/10", i === now && "border-primary text-primary ring-2 ring-primary/25", i > now && "text-muted-foreground")}>
            {i < now ? <Check className="size-3.5" aria-hidden /> : i + 1}
          </span>
          <span className={cn("text-[12px] leading-tight", i === now ? "font-medium text-foreground" : "text-muted-foreground")}>{step.label}</span>
        </li>
      ))}
    </ol>
  );
}
