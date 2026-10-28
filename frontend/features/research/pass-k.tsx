"use client";

// pass^k over k: how often a case succeeds every time it is run k times, per condition. A flat line is an agent that is
// consistent; a falling one fails some cases only sometimes. A public benchmark's curve, when there is one, is dashed and
// named, because its tasks are not the pack's.
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import type { LabResults } from "@/contracts/research";
import { Section } from "@/components/brain/primitives";
import { ChartContainer } from "@/components/ui/chart";
import { useReferences } from "./lab-api";
import { percent } from "./lab-ui";

const KS = [1, 2, 4, 8];
const COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)"];

export function PassKCurve({ data }: { data: LabResults }) {
  const references = (useReferences(data.experiment.paper).data ?? []).filter((r) => r.metricKey.startsWith("pass_hat_"));
  const at = (k: number, condition: string) => data.metrics.find((m) => m.key === `pass_hat_${k}` && m.condition === condition)?.value;
  const ks = KS.filter((k) => data.experiment.conditions.some((c) => at(k, c) !== undefined));
  if (ks.length < 2) return null;  // one point is not a curve
  const outside = references[0]?.benchmark;
  const rows = ks.map((k) => ({ k: `k=${k}`, ...Object.fromEntries(data.experiment.conditions.map((c) => [c, (at(k, c) ?? 0) * 100])),
    ...(outside ? { outside: (references.find((r) => r.metricKey === `pass_hat_${k}`)?.value ?? NaN) * 100 } : {}) }));
  const config = Object.fromEntries([...data.experiment.conditions.map((c, i) => [c, { label: data.conditions[c] ?? c, color: COLORS[i % COLORS.length] }]),
    ...(outside ? [["outside", { label: `${outside} (other tasks)`, color: "var(--muted-foreground)" }]] : [])]);
  return (
    <Section title="pass^k" description={outside ? `Each condition over k. Dashed: ${outside}, a different set of tasks, for scale only.` : "Each condition over k."}>
      <ChartContainer config={config} className="h-56 w-full">
        <LineChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="k" tickLine={false} axisLine={false} fontSize={13} />
          <YAxis unit="%" domain={[0, 100]} width={44} fontSize={12} />
          {data.experiment.conditions.map((c) => <Line key={c} dataKey={c} stroke={`var(--color-${c})`} strokeWidth={2} dot isAnimationActive={false} />)}
          {outside && <Line dataKey="outside" stroke="var(--color-outside)" strokeDasharray="4 4" strokeWidth={1.5} dot={false} isAnimationActive={false} />}
        </LineChart>
      </ChartContainer>
      <ul className="mt-3 space-y-1 text-[15px]">
        {data.experiment.conditions.map((c) => (
          <li key={c} className="flex justify-between"><span>{data.conditions[c] ?? c}</span>
            <span className="tabular">{ks.map((k) => `${percent(at(k, c) ?? 0)}`).join(" · ")}</span></li>
        ))}
      </ul>
    </Section>
  );
}
