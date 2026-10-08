"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { Policy } from "@/contracts";
import { Slider } from "@/components/ui/slider";
import { DataTable, type Column } from "@/components/brain/data-table";
import { PersonChip, useLookup } from "@/components/brain/names";
import { CritBadge, KeyValue, Mono, PageHeader, QueryView, Section, StatusChip } from "@/components/brain/primitives";
import { useNow, usePolicies, usePolicyVersions } from "@/lib/api/hooks";
import { date, pct } from "@/lib/format";
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

export function PolicyRegistry() {
  const policies = usePolicies();
    const router = useRouter();
  const lookup = useLookup();
  const now = useNow();
  const current = useMemo(() => (policies.data ?? []).filter((p) => p.branch === "main" && !p.supersededBy), [policies.data]);
  const columns: Column<Policy>[] = useMemo(
    () => [
      { id: "name", header: "Policy", width: "minmax(180px,1.4fr)", value: (p) => p.name, cell: (p) => <span className="font-medium">{p.name} <Mono className="text-muted-foreground">v{p.version}</Mono></span> },
      { id: "statement", header: "Statement", width: "minmax(240px,2.4fr)", value: (p) => p.statement, hideOnMobile: true, cell: (p) => <span className="truncate text-muted-foreground" title={p.statement}>{p.statement}</span> },
      { id: "crit", header: "Level", width: "56px", value: (p) => p.criticality, cell: (p) => <CritBadge level={p.criticality} /> },
      { id: "from", header: "Valid from", width: "110px", value: (p) => p.validFrom, hideOnMobile: true, cell: (p) => <span className="text-muted-foreground">{date(p.validFrom, lookup.tz)}</span> },
      { id: "signals", header: "Freshness", width: "120px", value: (p) => signals(p, now).filter((s) => s.fired).length, cell: (p) => {
        const n = signals(p, now).filter((s) => s.fired).length;
        return n ? <StatusChip tone={n > 1 ? "risk" : "warn"}>{n} signal{n > 1 ? "s" : ""}</StatusChip> : <StatusChip tone="ok">fresh</StatusChip>;
      } },
    ],
    [lookup.tz, now],
  );
  return (
    <div>
      <PageHeader title="Policy registry" description="Each version carries valid from, valid to, recorded at and superseded by. Freshness signals warn when a policy may be going stale. Nothing is invalidated without approval." />
      <QueryView query={policies}>
        {() => <DataTable label="Policies" data={current} columns={columns} getRowId={(p) => p.id} onRowClick={(p) => router.push(`/l2/policies/${p.key}`)} initialSort={{ id: "signals", desc: true }} height="calc(100dvh - 240px)" />}
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

function PolicyTimeline({ versions, now, tz }: { versions: Policy[]; now: number; tz?: string }) {
  const onMain = versions.filter((v) => v.branch === "main");
  const drafts = versions.filter((v) => v.branch !== "main");
  const all = [...onMain, ...drafts];
  const start = Math.min(...all.map((v) => Date.parse(v.validFrom)), ...all.map((v) => Date.parse(v.recordedAt)));
  const end = Math.max(now + 120 * 86_400_000, ...all.map((v) => Date.parse(v.validFrom) + 60 * 86_400_000));
  const [asOf, setAsOf] = useState(now);
  const pos = (t: number) => `${((t - start) / (end - start)) * 100}%`;
  const live = onMain.find((v) => !v.supersededBy) ?? onMain.at(-1)!;
  const trueThen = onMain.find((v) => Date.parse(v.validFrom) <= asOf && (!v.validTo || Date.parse(v.validTo) > asOf)) ?? null;
  const believedThen = [...onMain].filter((v) => Date.parse(v.recordedAt) <= asOf).sort((a, b) => b.version - a.version).find((v) => Date.parse(v.validFrom) <= asOf && (!v.validTo || Date.parse(v.validTo) > asOf || Date.parse(v.recordedAt) > asOf)) ?? null;
  const sigs = signals(live, now);
  return (
    <div>
      <PageHeader eyebrow={<Link href="/l2/policies" className="hover:underline">Policy registry</Link>} title={live.name} description={live.statement} actions={<CritBadge level={live.criticality} showLabel />} />
      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          <Section title="Validity timeline" description="Bars show when each version is true in the world. Ticks show when the system recorded it. Drafts on sandbox branches are dashed.">
            <div className="relative mt-2 space-y-2" role="list" aria-label="Policy versions">
              {all.map((v) => (
                <div key={v.id} role="listitem" className="relative h-9">
                  <div
                    className={cn("absolute top-1 flex h-7 items-center overflow-hidden whitespace-nowrap rounded-md border px-2 text-xs", v.branch === "main" ? "border-primary/40 bg-primary/12" : "border-dashed border-env-sandbox bg-env-sandbox/10")}
                    style={{ left: pos(Date.parse(v.validFrom)), width: `calc(${pos(v.validTo ? Date.parse(v.validTo) : end)} - ${pos(Date.parse(v.validFrom))})` }}
                    title={`v${v.version}: ${v.statement}`}
                  >
                    <span className="font-medium">v{v.version}</span>
                    <span className="ml-2 truncate text-muted-foreground">{String(v.rule.params.days ?? "")}{v.rule.params.days ? " days" : ""}</span>
                    {v.branch !== "main" && <span className="ml-2 text-env-sandbox">draft</span>}
                  </div>
                  <div className="absolute top-0 h-9 w-px bg-foreground/40" style={{ left: pos(Date.parse(v.recordedAt)) }} title={`recorded ${v.recordedAt.slice(0, 10)}`} />
                </div>
              ))}
              <div className="pointer-events-none absolute -top-1 bottom-0 w-0.5 bg-env-production" style={{ left: pos(asOf) }} aria-hidden />
            </div>
            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between text-xs">
                <span className="text-muted-foreground">As of</span>
                <span className="font-medium">{date(new Date(asOf).toISOString(), tz)}</span>
              </div>
              <Slider min={start} max={end} step={86_400_000} value={[asOf]} onValueChange={(v) => setAsOf(v[0])} aria-label="As of date" valueText={date(new Date(asOf).toISOString(), tz)} />
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2" aria-live="polite">
              <div className="rounded-lg border p-3">
                <div className="text-xs text-muted-foreground">What was true then (valid time)</div>
                <div className="mt-1 text-sm font-medium" data-testid="true-then">{trueThen ? `v${trueThen.version}: ${trueThen.statement}` : "No version valid"}</div>
              </div>
              <div className="rounded-lg border p-3">
                <div className="text-xs text-muted-foreground">What the system believed then (recorded time)</div>
                <div className="mt-1 text-sm font-medium" data-testid="believed-then">{believedThen ? `v${believedThen.version}: ${believedThen.statement}` : "Nothing recorded yet"}</div>
              </div>
            </div>
          </Section>
          <Section title="Versions">
            <ul className="divide-y text-sm">
              {all.map((v) => (
                <li key={v.id} className="py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Mono>v{v.version}</Mono>
                    <span>{v.statement}</span>
                    {v.branch !== "main" && <StatusChip tone="info">{v.branch}</StatusChip>}
                    {v.supersededBy && <StatusChip tone="neutral">superseded by {v.supersededBy.split("@")[1]}</StatusChip>}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    valid {date(v.validFrom, tz)} → {v.validTo ? date(v.validTo, tz) : "open"} · recorded {date(v.recordedAt, tz)}
                  </div>
                </li>
              ))}
            </ul>
          </Section>
        </div>
        <div className="space-y-4">
          <Section title="Freshness signals" description="Signals create invalidation proposals. Nothing is invalidated without approval.">
            <ul className="space-y-2">
              {sigs.map((s) => (
                <li key={s.key} className="flex items-start gap-2 text-sm">
                  {s.fired ? <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn-fg" aria-label="signal fired" /> : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-ok" aria-label="ok" />}
                  <span>
                    {s.label}
                    <span className="block text-xs text-muted-foreground">{s.detail}</span>
                  </span>
                </li>
              ))}
            </ul>
            {sigs.some((s) => s.fired) && (
              <Link href="/l2/vault" className="mt-3 inline-block text-xs text-primary hover:underline">
                See the librarian proposal
              </Link>
            )}
          </Section>
          <Section title="Details">
            <KeyValue items={[["Key", <Mono key="k">{live.key}</Mono>], ["Rule", <Mono key="r">{live.rule.kind}({Object.entries(live.rule.params).map(([k, v]) => `${k}=${v}`).join(", ")})</Mono>], ["DRI", <PersonChip key="d" id={live.dri} />]]} />
          </Section>
          <Section title="Dependents">
            <ul className="space-y-1 text-xs">
              {live.dependents.map((d) => (
                <li key={d.id}><Mono className="text-muted-foreground">{d.type}</Mono> {d.label}</li>
              ))}
            </ul>
          </Section>
        </div>
      </div>
    </div>
  );
}
