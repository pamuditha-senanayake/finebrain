"use client";

import { useReducedMotion } from "motion/react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { PageHeader, QueryView, Section, Status } from "@/components/brain/primitives";
import { useAnalytics, useOverview } from "@/lib/api/hooks";
import { FeatureUse } from "./feature-use";
import { AutonomyTrend, LegibilityMap } from "./overview-panels";
import { pct } from "@/lib/format";

const COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-1)"];

export function Analytics() {
  const reduceMotion = useReducedMotion();
  const analytics = useAnalytics();
  const overview = useOverview();
  return (
    <div>
      <PageHeader title="Progress and analytics" description="KPIs per cluster, loop performance, experiment outcomes, template completion, and where the brain is still blind." />
      <QueryView query={overview} rows={4}>
        {(o) => (
          <div className="mb-10 grid gap-6">
            <AutonomyTrend o={o} />
            <LegibilityMap o={o} />
          </div>
        )}
      </QueryView>
      <QueryView query={analytics}>
        {(a) => {
          const days = a.clusters[0]?.series.map((s) => s.day.slice(5)) ?? [];
          const runs = days.map((day, i) => Object.fromEntries([["day", day], ...a.clusters.map((c) => [c.clusterId, c.series[i]?.runs ?? 0])]));
          const autonomy = days.map((day, i) => Object.fromEntries([["day", day], ...a.clusters.map((c) => [c.clusterId, Math.round((c.series[i]?.autonomy ?? 0) * 100)])]));
          const config = Object.fromEntries(a.clusters.map((c, i) => [c.clusterId, { label: c.name, color: COLORS[i % COLORS.length] }])) satisfies ChartConfig;
          return (
            <div className="grid gap-6 xl:grid-cols-2 [&>*]:min-w-0">
              <Section title="Runs per day">
                <ChartContainer config={config} className="h-[240px] w-full">
                  <BarChart data={runs}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="day" tickLine={false} axisLine={false} fontSize={11} />
                    <YAxis tickLine={false} axisLine={false} fontSize={11} width={36} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <ChartLegend content={<ChartLegendContent />} />
                    {a.clusters.map((c) => (
                      <Bar isAnimationActive={!reduceMotion} key={c.clusterId} dataKey={c.clusterId} stackId="a" fill={`var(--color-${c.clusterId})`} radius={2} />
                    ))}
                  </BarChart>
                </ChartContainer>
              </Section>
              <Section title="Autonomy rate per cluster">
                <ChartContainer config={config} className="h-[240px] w-full">
                  <LineChart data={autonomy}>
                    <CartesianGrid vertical={false} />
                    <XAxis dataKey="day" tickLine={false} axisLine={false} fontSize={11} />
                    <YAxis tickLine={false} axisLine={false} fontSize={11} width={44} unit="%" />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <ChartLegend content={<ChartLegendContent />} />
                    {a.clusters.map((c) => (
                      <Line isAnimationActive={!reduceMotion} key={c.clusterId} dataKey={c.clusterId} stroke={`var(--color-${c.clusterId})`} strokeWidth={2} dot={false} type="monotone" />
                    ))}
                  </LineChart>
                </ChartContainer>
              </Section>
              <Section title="Loop performance">
                <table className="mini-table">
                  <thead className="text-left">
                    <tr>
                      <th className="py-1.5 font-medium">Loop</th>
                      <th className="py-1.5 text-right font-medium">Runs 7d</th>
                      <th className="py-1.5 text-right font-medium">Success</th>
                      <th className="py-1.5 text-right font-medium">Autonomy</th>
                    </tr>
                  </thead>
                  <tbody>
                    {a.loops.map((l) => (
                      <tr key={l.id} className="border-t">
                        <td className="py-1.5">{l.name}</td>
                        <td className="py-1.5 text-right tabular">{l.runs7d.toLocaleString()}</td>
                        <td className="py-1.5 text-right tabular">{pct(l.successRate)}</td>
                        <td className="py-1.5 text-right tabular">{pct(l.autonomyRate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Section>
              <Section title="Experiments">
                <ul className="divide-y text-sm">
                  {a.experiments.length === 0 && <li className="py-2 text-xs text-muted-foreground">No experiments</li>}
                  {a.experiments.map((e) => (
                    <li key={e.id} className="flex items-center justify-between gap-2 py-2">
                      <span>{e.title}</span>
                      <span className="flex gap-1.5">
                        <Status value={e.status} />
                        {e.impact && <Status value={e.impact} />}
                      </span>
                    </li>
                  ))}
                </ul>
              </Section>
              <Section title="Template completion" className="xl:col-span-2">
                <ul className="grid gap-x-10 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                  {a.templates.map((t) => (
                    <li key={t.id} className="text-xs">
                      <div className="mb-1 flex justify-between gap-2">
                        <span className="truncate">{t.name}</span>
                        <span className="tabular text-muted-foreground">{pct(t.completion)}</span>
                      </div>
                      <Progress value={t.completion * 100} className={cn("h-1.5", t.completion >= 1 ? "[&>[data-slot=progress-indicator]]:bg-ok/80" : "[&>[data-slot=progress-indicator]]:bg-warn")} aria-label={`${t.name} completion`} />
                    </li>
                  ))}
                </ul>
              </Section>
            </div>
          );
        }}
      </QueryView>
      <FeatureUse />
    </div>
  );
}
