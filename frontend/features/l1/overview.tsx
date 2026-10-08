"use client";

import { useReducedMotion } from "motion/react";
import { Check, EyeOff, Minus } from "lucide-react";
import Link from "next/link";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { AmbientSurface, NumberTween } from "@/components/brain/motion";
import { useLookup } from "@/components/brain/names";
import { Kpi, PageHeader, QueryView, Section, StatusChip } from "@/components/brain/primitives";
import { useClusters, useOverview } from "@/lib/api/hooks";
import { money, pct, usd } from "@/lib/format";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

const trendConfig = {
  autonomy: { label: "Autonomy", color: "var(--chart-1)" },
  escalation: { label: "Escalation", color: "var(--chart-4)" },
} satisfies ChartConfig;

export function Overview() {
  const reduceMotion = useReducedMotion();
  const overview = useOverview();
  const clusters = useClusters();
  const lookup = useLookup();
  const clusterId = useUi((s) => s.clusterId);
  return (
    <div>
      <AmbientSurface className="-mx-3 -mt-4 mb-5 rounded-b-2xl border-b px-3 pb-5 pt-6 sm:-mx-6 sm:-mt-5 sm:px-6">
        <div className="relative">
          <PageHeader title="Brain overview" description="Every cluster at once: how much work finishes without a person, what is at stake, and where the brain is still blind." />
          <QueryView query={overview} rows={2}>
            {(o) => (
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
                <Kpi label="Runs, last 24 hours" value={<NumberTween value={o.totals.runs24h} />} />
                <Kpi label="Autonomy rate" value={<NumberTween value={o.totals.autonomyRate * 100} format={(n) => `${n.toFixed(0)}%`} />} hint="finished without a person" tone="ok" />
                <Kpi label="Escalation rate" value={pct(o.totals.escalationRate, 1)} />
                <Kpi label="Money at stake" value={money(o.totals.moneyAtStakeMinor, lookup.currency, { compact: true })} />
                <Kpi label="Open risks" value={o.totals.openRisks} tone={o.totals.openRisks > 5 ? "risk" : "warn"} hint={<Link href="/l1/entity" className="hover:underline">risk register</Link>} />
                <Kpi label="Cost per resolved task" value={usd(o.totals.costPerResolvedUsd)} />
              </div>
            )}
          </QueryView>
        </div>
      </AmbientSurface>

      <QueryView query={overview}>
        {(o) => (
          <div className="space-y-4">
            <div>
              <h2 className="mb-2 text-sm font-semibold">Clusters</h2>
              <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {(clusters.data ?? []).map((c) => {
                  const k = o.kpis.find((x) => x.clusterId === c.id);
                  const planned = c.status === "planned";
                  return (
                    <li key={c.id} className={cn("rounded-xl border bg-card p-3", planned && "border-dashed bg-transparent", clusterId === c.id && "ring-2 ring-primary/40")}>
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <h3 className="text-sm font-semibold">{c.name}</h3>
                          <p className="line-clamp-2 text-[11px] text-muted-foreground">{c.description}</p>
                        </div>
                        {planned ? <StatusChip tone="neutral">planned</StatusChip> : <HealthRing value={c.health} />}
                      </div>
                      {!planned && k && (
                        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                          <dt className="text-muted-foreground">Autonomy</dt>
                          <dd className="text-right tabular">{pct(k.autonomyRate)}</dd>
                          <dt className="text-muted-foreground">Escalations</dt>
                          <dd className="text-right tabular">{pct(k.escalationRate, 1)}</dd>
                          <dt className="text-muted-foreground">Money at stake</dt>
                          <dd className="text-right tabular">{money(k.moneyAtStakeMinor, lookup.currency, { compact: true })}</dd>
                          <dt className="text-muted-foreground">Cost per task</dt>
                          <dd className="text-right tabular">{usd(k.costPerResolvedUsd)}</dd>
                          <dt className="text-muted-foreground">Runs 24h</dt>
                          <dd className="text-right tabular">{k.runs24h}</dd>
                        </dl>
                      )}
                      {planned && <p className="mt-3 text-[11px] text-muted-foreground">Plugs in the same way as the active clusters. No sensors connected yet.</p>}
                    </li>
                  );
                })}
              </ul>
            </div>
            <div className="grid gap-4 xl:grid-cols-[1fr_1.4fr]">
              <Section title="Autonomy and escalation, 14 days">
                <ChartContainer config={trendConfig} className="h-[260px] w-full">
                  <AreaChart data={o.trend.map((t) => ({ ...t, autonomy: Math.round(t.autonomy * 100), escalation: Math.round(t.escalation * 1000) / 10, day: t.day.slice(5) }))} margin={{ left: 0, right: 8, top: 8 }}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="day" tickLine={false} axisLine={false} fontSize={11} />
                    <YAxis tickLine={false} axisLine={false} fontSize={11} width={44} unit="%" />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Area isAnimationActive={!reduceMotion} dataKey="autonomy" type="monotone" fill="var(--color-autonomy)" fillOpacity={0.15} stroke="var(--color-autonomy)" strokeWidth={2} />
                    <Area isAnimationActive={!reduceMotion} dataKey="escalation" type="monotone" fill="var(--color-escalation)" fillOpacity={0.12} stroke="var(--color-escalation)" strokeWidth={2} />
                  </AreaChart>
                </ChartContainer>
              </Section>
              <Section title="Legibility map" description="Each activity against four checks. Gaps are where the brain still cannot see.">
                <div className="max-h-[300px] overflow-auto scrollbar-thin" tabIndex={0} aria-label="Legibility map, scrollable">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-card text-[10px] uppercase tracking-wide text-muted-foreground">
                      <tr>
                        <th className="py-1.5 text-left font-medium">Activity</th>
                        {["Sensed", "Skilled", "Governed", "Reported"].map((h) => (
                          <th key={h} className="w-16 py-1.5 text-center font-medium">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {o.legibility
                        .filter((l) => clusterId === "all" || l.clusterId === clusterId)
                        .map((l) => (
                          <tr key={l.activity} className="border-t">
                            <td className="py-1.5 pr-2">
                              <div className="truncate font-medium">{l.activity}</div>
                              <div className="truncate text-[10px] text-muted-foreground">{l.agent}</div>
                            </td>
                            {[l.sensed, l.skilled, l.governed, l.reported].map((v, i) => (
                              <td key={i} className="text-center">
                                {v ? <Check className="mx-auto size-3.5 text-ok" aria-label="yes" /> : <EyeOff className="mx-auto size-3.5 text-risk" aria-label="gap" />}
                              </td>
                            ))}
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <Minus className="size-3" /> {o.legibility.filter((l) => !(l.sensed && l.skilled && l.governed && l.reported)).length} of {o.legibility.length} activities have at least one gap.
                </p>
              </Section>
            </div>
          </div>
        )}
      </QueryView>
    </div>
  );
}

function HealthRing({ value }: { value: number }) {
  const r = 14;
  const c = 2 * Math.PI * r;
  const tone = value >= 85 ? "var(--ok)" : value >= 70 ? "var(--warn)" : "var(--risk)";
  return (
    <svg width="36" height="36" viewBox="0 0 36 36" role="img" aria-label={`Health ${value}`}>
      <circle cx="18" cy="18" r={r} fill="none" stroke="var(--muted)" strokeWidth="4" />
      <circle cx="18" cy="18" r={r} fill="none" stroke={tone} strokeWidth="4" strokeDasharray={c} strokeDashoffset={c * (1 - value / 100)} strokeLinecap="round" transform="rotate(-90 18 18)" />
      <text x="18" y="21.5" textAnchor="middle" fontSize="10" fontWeight="600" fill="currentColor">{value}</text>
    </svg>
  );
}
