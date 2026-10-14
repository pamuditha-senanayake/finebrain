"use client";

import { useState } from "react";
import { WorkflowFilter, countByMany } from "@/components/brain/category-filter";
import { useWorkflowIndex } from "@/lib/workflow-index";
import type { Template } from "@/contracts";
import { AgentChip, PersonChip, useLookup } from "@/components/brain/names";
import { KeyValue, Mono, PageHeader, QueryView, Section, Status } from "@/components/brain/primitives";
import { useSensors, useTemplates } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

export function Templates() {
  const templates = useTemplates();
  const sensors = useSensors();
  const lookup = useLookup();
  const index = useWorkflowIndex();
  const [wf, setWf] = useState("all");
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div>
      <PageHeader title="Templates" description="Information contracts: the fields each agent must bring back, from which sensors, how fresh, with which evidence, on what cadence, and who owns them." />
      <QueryView query={templates}>
        {(all) => {
          const list = wf === "all" ? all : all.filter((x) => index.of("template", x.id).includes(wf));
          const t: Template = list.find((x) => x.id === selected) ?? list[0] ?? all[0];
          return (
            <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
              <div className="space-y-2">
              <WorkflowFilter value={wf} onChange={setWf} options={countByMany(all, (x) => index.of("template", x.id))} />
              <ul className="max-h-[calc(100dvh-270px)] space-y-1 overflow-auto scrollbar-thin" tabIndex={0} aria-label="Templates">
                {list.slice(0, 200).map((x) => (
                  <li key={x.id}>
                    <button type="button" onClick={() => setSelected(x.id)} aria-current={x.id === t.id} className={cn("flex w-full items-center justify-between gap-2 rounded-lg border bg-card px-3 py-2 text-left text-sm hover:border-primary/40", x.id === t.id && "border-primary/50 bg-accent/40")}>
                      <span className="truncate">{x.name}</span>
                      <Status value={x.status} />
                    </button>
                  </li>
                ))}
              </ul>
              </div>
              <div className="space-y-4">
                <Section title={t.name} description={lookup.cluster(t.clusterId)}>
                  <KeyValue
                    items={[
                      ["Workflows", index.of("template", t.id).join(", ") || "none"],
                      ["Cadence", t.cadence],
                      ["Owner", <PersonChip key="o" id={t.owner} />],
                      ["Assigned agents", <span key="a" className="flex flex-wrap gap-2">{t.assignedAgents.map((a) => <AgentChip key={a} id={a} />)}</span>],
                      ["Freshness rule", t.freshnessRule],
                      ["Required evidence", t.requiredEvidence.join(", ") || "none"],
                    ]}
                  />
                </Section>
                <Section title="Fields">
                  <table className="w-full text-sm">
                    <thead className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                      <tr>
                        <th className="py-1.5 font-medium">Field</th>
                        <th className="py-1.5 font-medium">Source sensors</th>
                        <th className="py-1.5 font-medium">Fresh within</th>
                        <th className="py-1.5 font-medium">Required</th>
                      </tr>
                    </thead>
                    <tbody>
                      {t.fields.map((f) => (
                        <tr key={f.key} className="border-t">
                          <td className="py-1.5">{f.label} <Mono className="text-muted-foreground">{f.key}</Mono></td>
                          <td className="py-1.5 text-xs">{f.sensors.map((s) => sensors.data?.find((x) => x.id === s)?.name ?? s).join(", ") || "graph"}</td>
                          <td className="py-1.5 text-xs">{f.freshnessHours} h</td>
                          <td className="py-1.5 text-xs">{f.required ? "yes" : "no"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Section>
              </div>
            </div>
          );
        }}
      </QueryView>
    </div>
  );
}
