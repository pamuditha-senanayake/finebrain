"use client";

import { AlertTriangle, CheckCircle2, Maximize2, Pencil } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Policy } from "@/contracts";
import { CategoryFilter, WorkflowFilter, countBy, countByMany } from "@/components/brain/category-filter";
import { DataTable, type Column } from "@/components/brain/data-table";
import { PersonChip, useLookup } from "@/components/brain/names";
import { CritBadge, KeyValue, Mono, PageHeader, QueryView, StatusChip } from "@/components/brain/primitives";
import { useBrainMap, useNow, usePolicies, usePolicyVersions, useStudioWorkflows } from "@/lib/api/hooks";
import { date, pct } from "@/lib/format";
import { useCurrentUser } from "@/lib/auth";
import { useStudio } from "@/features/studio/state";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function signals(p: Policy, now: number) {
  return [
    { key: "interval", label: "Validity interval closed", fired: p.freshness.intervalClosed || (!!p.validTo && Date.parse(p.validTo) < now), detail: p.validTo ? `valid to ${p.validTo.slice(0, 10)}` : "open" },
    { key: "drift", label: "Observed behaviour shows a drift point", fired: !!p.freshness.driftPointAt, detail: p.freshness.driftPointAt ? `since ${p.freshness.driftPointAt.slice(0, 10)}` : "none" },
    { key: "conformance", label: "Documented policy matches observed runs", fired: p.freshness.conformance < 0.8, detail: pct(p.freshness.conformance) },
    { key: "evidence", label: "Newer evidence conflicts", fired: p.freshness.conflictingEvidence > 0, detail: `${p.freshness.conflictingEvidence} conflicting` },
    { key: "reliance", label: "Answers rely on outdated policy", fired: p.freshness.outdatedRelianceRate > 0.1, detail: pct(p.freshness.outdatedRelianceRate) },
  ];
}

const CATEGORY_BY_RULE: Record<string, string> = {
  max_days_since_purchase: "financial limits",
  max_amount_minor: "financial limits",
  mask_by_default: "privacy and data",
  retention_days: "privacy and data",
  tone_gate: "communication",
  requires_l1: "approvals",
  evidence_required: "compliance",
  periodic_review: "security and access",
};
/** A policy's category, from the kind of rule it enforces. */
export const policyCategory = (p: Policy) => CATEGORY_BY_RULE[p.rule.kind] ?? "general";

export function PolicyRegistry() {
  const policies = usePolicies();
  const map = useBrainMap();
  const [category, setCategory] = useState("all");
  const [wf, setWf] = useState("all");
  const router = useRouter();
  const lookup = useLookup();
  const now = useNow();
  const current = useMemo(() => (policies.data ?? []).filter((p) => p.branch === "main" && !p.supersededBy), [policies.data]);
  // Which workflows use each policy, read from the workflow maps.
  const workflowsOf = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const w of map.data?.workflows ?? []) for (const i of w.items) if (i.kind === "policy") {
      const key = i.id.split(".policy.")[1];
      if (key) m.set(key, [...(m.get(key) ?? []), w.name]);
    }
    return m;
  }, [map.data]);
  const columns: Column<Policy>[] = useMemo(
    () => [
      { id: "name", header: "Policy", width: "minmax(180px,1.4fr)", value: (p) => p.name, cell: (p) => <span className="font-medium">{p.name} <Mono className="text-muted-foreground">v{p.version}</Mono></span> },
      { id: "category", header: "Category", width: "150px", value: (p) => policyCategory(p), cell: (p) => <StatusChip tone="info" className="capitalize">{policyCategory(p)}</StatusChip> },
      { id: "workflow", header: "Workflow", width: "minmax(160px,1.2fr)", value: (p) => (workflowsOf.get(p.key) ?? []).join(", "), cell: (p) => { const w = workflowsOf.get(p.key) ?? []; return w.length ? <span className="truncate" title={w.join(", ")}>{w[0]}{w.length > 1 && <span className="text-muted-foreground"> +{w.length - 1}</span>}</span> : <span className="text-muted-foreground">none</span>; } },
      { id: "statement", header: "Statement", width: "minmax(240px,2.4fr)", value: (p) => p.statement, hideOnMobile: true, cell: (p) => <span className="truncate text-muted-foreground" title={p.statement}>{p.statement}</span> },
      { id: "crit", header: "Level", width: "56px", value: (p) => p.criticality, cell: (p) => <CritBadge level={p.criticality} /> },
      { id: "from", header: "Valid from", width: "110px", value: (p) => p.validFrom, hideOnMobile: true, cell: (p) => <span className="text-muted-foreground">{date(p.validFrom, lookup.tz)}</span> },
      { id: "signals", header: "Freshness", width: "120px", value: (p) => signals(p, now).filter((s) => s.fired).length, cell: (p) => {
        const n = signals(p, now).filter((s) => s.fired).length;
        return n ? <StatusChip tone={n > 1 ? "risk" : "warn"}>{n} signal{n > 1 ? "s" : ""}</StatusChip> : <StatusChip tone="ok">fresh</StatusChip>;
      } },
    ],
    [lookup.tz, now, workflowsOf],
  );
  return (
    <div>
      <PageHeader title="Policy registry" description="Each version carries valid from, valid to, recorded at and superseded by. Freshness signals warn when a policy may be going stale. Nothing is invalidated without approval." />
      <QueryView query={policies}>
        {() => <DataTable label="Policies" data={current.filter((p) => (category === "all" || policyCategory(p) === category) && (wf === "all" || (workflowsOf.get(p.key) ?? []).includes(wf)))} columns={columns} getRowId={(p) => p.id} onRowClick={(p) => router.push(`/l2/policies/${p.key}`)} initialSort={{ id: "signals", desc: true }} height="calc(100dvh - 240px)" toolbar={<><CategoryFilter label="Filter by category" allLabel="All categories" value={category} onChange={setCategory} options={countBy(current, policyCategory)} /><WorkflowFilter value={wf} onChange={setWf} options={countByMany(current, (p) => workflowsOf.get(p.key) ?? [])} /></>} />}
      </QueryView>
    </div>
  );
}

export function PolicyDetail() {
  const { key } = useParams<{ key: string }>();
  const versions = usePolicyVersions(key);
    const lookup = useLookup();
  const now = useNow();
  return (
    <QueryView query={versions}>
      {(vs) => <PolicyTimeline versions={vs} now={now} tz={lookup.tz} />}
    </QueryView>
  );
}

const DAY = 86_400_000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function PolicyTimeline({ versions, now, tz }: { versions: Policy[]; now: number; tz?: string }) {
  const onMain = versions.filter((v) => v.branch === "main");
  const drafts = versions.filter((v) => v.branch !== "main");
  const all = [...onMain, ...drafts];
  const live = onMain.find((v) => !v.supersededBy) ?? onMain.at(-1)!;
  const [selectedId, setSelectedId] = useState<string>(live.id);
  const [signalKey, setSignalKey] = useState<string | null>(null);
  const selected = all.find((v) => v.id === selectedId) ?? live;
  const fitStart = Math.min(...all.map((v) => Date.parse(v.validFrom)), ...all.map((v) => Date.parse(v.recordedAt))) - 20 * DAY;
  const fitEnd = Math.max(now + 120 * DAY, ...all.map((v) => Date.parse(v.validFrom) + 60 * DAY));
  // The visible time window. Drag to move through time, scroll to zoom around the cursor.
  const [dom, setDom] = useState<{ start: number; end: number } | null>(null);
  const start = dom?.start ?? fitStart;
  const end = dom?.end ?? fitEnd;
  const plot = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; start: number; end: number; moved: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);
  const suppress = useRef(false);
  const win = useRef({ start, end });
  useEffect(() => {
    win.current = { start, end };
  }, [start, end]);
  useEffect(() => {
    const el = plot.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const { start: a, end: b } = win.current;
      const at = a + ((e.clientX - r.left) / r.width) * (b - a);
      const f = Math.exp(e.deltaY * 0.0015);
      const span = Math.min(Math.max((b - a) * f, 14 * DAY), (fitEnd - fitStart) * 4);
      const k = (at - a) / (b - a);
      setDom({ start: at - k * span, end: at + (1 - k) * span });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [fitStart, fitEnd]);
  const pos = (t: number) => `${((t - start) / (end - start)) * 100}%`;
  const sigs = signals(live, now);
  const { user } = useCurrentUser();
  const studio = useStudioWorkflows();
  const setDraft = useStudio((st) => st.setDraft);
  const canEdit = !!user && user.tier !== "L3";
  // The workflows that use this policy, so the edit opens where the policy lives.
  const studioLinks = (studio.data ?? []).flatMap((w) => {
    const item = w.members.find((m) => m.endsWith(`.policy.${live.key}`));
    return item ? [{ name: w.name, href: `/studio?wf=${w.id}&focus=${encodeURIComponent(item)}&view=chat` }] : [];
  });
  const activeSignal = sigs.find((s) => s.key === signalKey) ?? null;
  // Freshness markers: dated signals sit at their date, the rest gather at today.
  const markerAt = (key: string): number =>
    key === "interval" && live.validTo ? Date.parse(live.validTo) : key === "drift" && live.freshness.driftPointAt ? Date.parse(live.freshness.driftPointAt) : now;
  // Month ticks along the top.
  const ticks: { t: number; label: string }[] = [];
  const d0 = new Date(start);
  for (let t = Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth() + 1, 1); t < end && ticks.length < 400; ) {
    const d = new Date(t);
    ticks.push({ t, label: d.getUTCMonth() === 0 ? `${MONTHS[0]} ${d.getUTCFullYear()}` : MONTHS[d.getUTCMonth()] });
    t = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
  }
  const every = Math.max(1, Math.ceil(ticks.length / 14));
  const panel = "rounded-xl border bg-card/90 shadow-md backdrop-blur";
  return (
    <div className="relative -mx-3 -my-4 h-[calc(100dvh-3rem)] min-h-[520px] overflow-hidden sm:-mx-6 sm:-my-5">
      <h1 className="sr-only">{live.name}</h1>
      {/* title, top left */}
      <div className="absolute left-3 top-3 z-10 flex flex-wrap items-center gap-2">
        <Link href="/l2/policies" className={`${panel} px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground`}>
          ← Policy registry
        </Link>
        <div className={`${panel} flex items-center gap-2 px-3 py-1.5`}>
          <span className="text-sm font-semibold">{live.name}</span>
          <CritBadge level={live.criticality} showLabel />
          <StatusChip tone="info" className="capitalize">{policyCategory(live)}</StatusChip>
        </div>
        <button type="button" onClick={() => setDom(null)} className={`${panel} inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground`} aria-label="Fit the whole timeline">
          <Maximize2 className="size-3.5" /> Fit
        </button>
        <span className="hidden text-[11px] text-muted-foreground sm:inline">Drag to move · scroll to zoom</span>
      </div>

      {/* the graph: fills the page. Bars are versions, clickable. */}
      <div className="absolute inset-0 pb-6 pt-16 lg:pr-[368px]" role="group" aria-label="Validity timeline">
        <div
          ref={plot}
          className={cn("relative mx-4 h-full touch-none select-none overflow-hidden", dragging ? "cursor-grabbing" : "cursor-grab")}
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            drag.current = { x: e.clientX, start, end, moved: false };
          }}
          onPointerMove={(e) => {
            const d = drag.current;
            const el = plot.current;
            if (!d || !el) return;
            const dx = e.clientX - d.x;
            if (!d.moved && Math.abs(dx) < 4) return;
            if (!d.moved) {
              d.moved = true;
              setDragging(true);
              el.setPointerCapture(e.pointerId);
            }
            const shift = (dx / el.clientWidth) * (d.end - d.start);
            setDom({ start: d.start - shift, end: d.end - shift });
          }}
          onPointerUp={() => {
            if (drag.current?.moved) suppress.current = true;
            drag.current = null;
            setDragging(false);
          }}
          onClickCapture={(e) => {
            if (suppress.current) {
              suppress.current = false;
              e.stopPropagation();
              e.preventDefault();
            }
          }}
        >
          <div className="absolute inset-x-0 top-0 h-6 border-b text-[10px] text-muted-foreground" aria-hidden>
            {ticks.map((k, i) => (
              <span key={k.t} className={cn("absolute top-0 -translate-x-1/2", i % every !== 0 && "hidden")} style={{ left: pos(k.t) }}>{k.label}</span>
            ))}
          </div>
          {ticks.map((k, i) => (
            <div key={`g-${k.t}`} className={cn("absolute bottom-0 top-6 w-px bg-border/50", i % every !== 0 && "hidden")} style={{ left: pos(k.t) }} aria-hidden />
          ))}
          {/* today */}
          <div className="pointer-events-none absolute bottom-0 top-6 w-0.5 bg-env-production" style={{ left: pos(now) }} aria-hidden />
          <span className="pointer-events-none absolute bottom-0 -translate-x-1/2 rounded bg-env-production px-1.5 py-0.5 text-[10px] font-medium text-white" style={{ left: pos(now) }}>today</span>

          {/* freshness markers */}
          <div className="absolute inset-x-0 top-8 h-12" role="group" aria-label="Freshness signals">
            {sigs.map((s, i) => {
              const at = markerAt(s.key);
              const dated = s.key === "interval" || s.key === "drift";
              return (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => setSignalKey(signalKey === s.key ? null : s.key)}
                  aria-pressed={signalKey === s.key}
                  title={`${s.label}: ${s.detail}`}
                  className={cn("absolute grid size-6 -translate-x-1/2 place-items-center rounded-full border bg-card shadow-sm transition-transform hover:scale-110 focus-visible:outline-2", s.fired ? "border-warn text-warn-fg" : "text-ok opacity-70", signalKey === s.key && "ring-2 ring-primary")}
                  style={{ left: dated ? pos(at) : `calc(${pos(at)} + ${(i - 2) * 26}px)`, top: dated ? 0 : 24 }}
                >
                  {s.fired ? <AlertTriangle className="size-3.5" aria-label="signal fired" /> : <CheckCircle2 className="size-3.5" aria-label="ok" />}
                </button>
              );
            })}
          </div>

          {/* version bars */}
          <div className="absolute inset-x-0 bottom-8 top-24 flex flex-col justify-center gap-4" role="list" aria-label="Policy versions">
            {all.map((v) => {
              const on = v.id === selected.id;
              return (
                <div key={v.id} role="listitem" className="relative h-14">
                  <button
                    type="button"
                    onClick={() => setSelectedId(v.id)}
                    aria-pressed={on}
                    aria-label={`Version ${v.version}${v.branch !== "main" ? `, draft on ${v.branch}` : ""}. Show details.`}
                    className={cn(
                      "absolute top-1 flex h-12 items-center gap-2 overflow-hidden whitespace-nowrap rounded-lg border px-3 text-left text-sm transition-shadow hover:shadow-md focus-visible:outline-2",
                      v.branch === "main" ? "border-primary/40 bg-primary/12" : "border-dashed border-env-sandbox bg-env-sandbox/10",
                      on && "ring-2 ring-primary",
                    )}
                    style={{ left: pos(Date.parse(v.validFrom)), width: `calc(${pos(v.validTo ? Date.parse(v.validTo) : end)} - ${pos(Date.parse(v.validFrom))})` }}
                  >
                    <span className="font-semibold">v{v.version}</span>
                    <span className="truncate text-muted-foreground">{v.statement}</span>
                    {v.branch !== "main" && <span className="shrink-0 text-xs text-env-sandbox">draft</span>}
                  </button>
                  <div className="pointer-events-none absolute top-0 h-14 w-px bg-foreground/40" style={{ left: pos(Date.parse(v.recordedAt)) }} title={`recorded ${v.recordedAt.slice(0, 10)}`} />
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* boxes inside the graph */}
      <div className="absolute bottom-3 right-3 top-14 z-10 hidden w-[344px] flex-col gap-3 overflow-auto lg:flex">
        <section className={`${panel} p-3`} aria-label="Selected version">
          <div className="flex items-center gap-2">
            <Mono className="text-sm font-semibold">v{selected.version}</Mono>
            {selected.branch !== "main" && <StatusChip tone="info">{selected.branch}</StatusChip>}
            {selected.supersededBy && <StatusChip tone="neutral">superseded by {selected.supersededBy.split("@")[1]}</StatusChip>}
          </div>
          <p className="mt-1.5 text-sm">{selected.statement}</p>
          <p className="mt-1.5 text-xs text-muted-foreground">
            Valid {date(selected.validFrom, tz)} → {selected.validTo ? date(selected.validTo, tz) : "open"} · recorded {date(selected.recordedAt, tz)}
          </p>
        </section>
        {canEdit && (
          <section className={`${panel} p-3`} aria-label="Change this policy">
            {studioLinks.length > 0 ? (
              <div className="space-y-2">
                {studioLinks.map((l, i) => (
                  <Button key={l.href} asChild size="sm" variant={i === 0 ? "default" : "outline"} className="w-full">
                    <Link href={l.href} onClick={() => setDraft(`Change the "${live.name}" policy: `)}>
                      <Pencil /> Change this policy{studioLinks.length > 1 ? ` in ${l.name}` : " in Workflow Studio"}
                    </Link>
                  </Button>
                ))}
                <p className="text-[11px] text-muted-foreground">Opens the workflow that uses this policy. Edits are reviewed before anyone confirms them.</p>
              </div>
            ) : (
              <Button asChild size="sm" variant="outline" className="w-full">
                <Link href="/studio" onClick={() => setDraft(`Change the "${live.name}" policy: `)}><Pencil /> Open Workflow Studio</Link>
              </Button>
            )}
          </section>
        )}
        {activeSignal && (
          <section className={`${panel} border-warn/40 p-3`} aria-label="Freshness signal">
            <div className="flex items-start gap-2 text-sm">
              {activeSignal.fired ? <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn-fg" /> : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-ok" />}
              <span>
                {activeSignal.label}
                <span className="block text-xs text-muted-foreground">{activeSignal.detail}</span>
              </span>
            </div>
            {activeSignal.fired && (
              <Link href="/l2/vault" className="mt-2 inline-block text-xs text-primary hover:underline">
                See the librarian proposal
              </Link>
            )}
          </section>
        )}
        <section className={`${panel} p-3`} aria-label="Details">
          <h2 className="mb-2 text-xs font-semibold">Details</h2>
          <KeyValue items={[["Key", <Mono key="k">{live.key}</Mono>], ["Rule", <Mono key="r">{live.rule.kind}({Object.entries(live.rule.params).map(([k, v]) => `${k}=${v}`).join(", ")})</Mono>], ["DRI", <PersonChip key="d" id={live.dri} />]]} />
        </section>
        <section className={`${panel} p-3`} aria-label="Dependents">
          <h2 className="mb-2 text-xs font-semibold">Dependents</h2>
          <ul className="space-y-1 text-xs">
            {live.dependents.length === 0 && <li className="text-muted-foreground">Nothing depends on it yet</li>}
            {live.dependents.map((d) => (
              <li key={d.id}><Mono className="text-muted-foreground">{d.type}</Mono> {d.label}</li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
