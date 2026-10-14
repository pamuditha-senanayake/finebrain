"use client";

import { useReducedMotion } from "motion/react";
import { Check, EyeOff, Minus } from "lucide-react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import type { Overview } from "@/contracts";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Section } from "@/components/brain/primitives";
import { useUi } from "@/lib/store";

const trendConfig = {
  autonomy: { label: "Autonomy", color: "var(--chart-1)" },
  escalation: { label: "Escalation", color: "var(--chart-4)" },
} satisfies ChartConfig;

export function AutonomyTrend({ o }: { o: Overview }) {
  const reduceMotion = useReducedMotion();
  return (
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
  );
}

export function LegibilityMap({ o }: { o: Overview }) {
  const clusterId = useUi((s) => s.clusterId);
  return (
    <Section title="Legibility map" description="Each activity against four checks. Gaps are where the brain still cannot see.">
      <div className="max-h-[360px] overflow-auto rounded-xl border scrollbar-thin" tabIndex={0} aria-label="Legibility map, scrollable">
        <table className="w-full text-[13px]">
          <thead className="sticky top-0 z-10 bg-table-head text-[11px] uppercase tracking-[0.07em] text-foreground/65">
            <tr>
              <th className="px-4 py-2.5 text-left font-semibold">Activity</th>
              {["Sensed", "Skilled", "Governed", "Reported"].map((h) => (
                <th key={h} className="w-24 px-2 py-2.5 text-center font-semibold">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {o.legibility
              .filter((l) => clusterId === "all" || l.clusterId === clusterId)
              .map((l) => (
                <tr key={l.activity} className="border-t border-border/70 even:bg-table-stripe">
                  <td className="px-4 py-2.5">
                    <div className="truncate font-medium">{l.activity}</div>
                    <div className="truncate text-[11px] text-muted-foreground">{l.agent}</div>
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
  );
}
