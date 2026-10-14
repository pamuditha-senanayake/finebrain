"use client";

import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { Skill, SkillStep } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CategoryFilter, countBy } from "@/components/brain/category-filter";
import { DataTable, type Column } from "@/components/brain/data-table";
import { AgentChip, PersonChip, useLookup } from "@/components/brain/names";
import { EmptyState, KeyValue, Mono, PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useAgents, useOp, useSkills, useSkillVersions, useStudioWorkflows } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { pct, relTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function HealthBars({ s }: { s: Skill }) {
  const rows: [string, number, string][] = [
    ["Task success", s.health.taskSuccess, "finished runs that succeeded without a person"],
    [`Consistency pass^${s.health.k}`, s.health.consistencyPassK, `all ${s.health.k} repeated runs of a case pass`],
    ["Conformance", s.health.conformance, "how closely observed runs follow the documented steps"],
  ];
  return (
    <ul className="space-y-2.5">
      {rows.map(([label, v, hint]) => (
        <li key={label} className="text-xs">
          <div className="mb-1 flex justify-between">
            <span title={hint}>{label}</span>
            <span className={cn("tabular", v < 0.75 ? "text-risk" : v < 0.85 ? "text-warn-fg" : "text-ok")}>{pct(v)}</span>
          </div>
          <Progress value={v * 100} className="h-1.5" aria-label={label} />
        </li>
      ))}
    </ul>
  );
}

export function SkillsStudio() {
  const skills = useSkills();
  const agents = useAgents();
  const router = useRouter();
  const lookup = useLookup();
  const workflows = useStudioWorkflows();
  const [category, setCategory] = useState("all");
  // Related workflows come from each workflow's members; a skill's category is its first workflow's lead topic.
  const info = useMemo(() => {
    const m = new Map<string, { workflows: string[]; category: string }>();
    for (const w of workflows.data ?? []) for (const id of w.members) {
      const [, kind, skillId] = id.split(".");
      if (kind !== "skill" || !skillId) continue;
      const cur = m.get(skillId) ?? { workflows: [], category: w.topics[0] ?? "general" };
      cur.workflows.push(w.name);
      m.set(skillId, cur);
    }
    return m;
  }, [workflows.data]);
  const categoryOf = (s: Skill) => info.get(s.id)?.category ?? "general";
  const main = useMemo(() => (skills.data ?? []).filter((s) => s.branch === "main" && s.status === "active"), [skills.data]);
  const drafts = useMemo(() => (skills.data ?? []).filter((s) => s.status === "draft"), [skills.data]);
  const columns: Column<Skill>[] = useMemo(
    () => [
      { id: "name", header: "Skill", width: "minmax(200px,1.6fr)", value: (s) => s.name, cell: (s) => <span className="font-medium">{s.name} <Mono className="text-muted-foreground">v{s.version}</Mono></span> },
      { id: "category", header: "Category", width: "120px", value: (s) => categoryOf(s), cell: (s) => <StatusChip tone="info" className="capitalize">{categoryOf(s)}</StatusChip> },
      { id: "workflow", header: "Related workflows", width: "minmax(180px,1.3fr)", value: (s) => (info.get(s.id)?.workflows ?? []).join(", "), cell: (s) => { const w = info.get(s.id)?.workflows ?? []; return w.length ? <span className="truncate" title={w.join(", ")}>{w.join(", ")}</span> : <span className="text-muted-foreground">none</span>; } },
      { id: "agent", header: "Agent", width: "minmax(140px,1fr)", value: (s) => lookup.name(s.agentIds[0] ?? ""), hideOnMobile: true, cell: (s) => (s.agentIds[0] ? <AgentChip id={s.agentIds[0]} link={false} /> : null) },
      { id: "success", header: "Success", width: "80px", align: "right", value: (s) => s.health.taskSuccess, cell: (s) => pct(s.health.taskSuccess) },
      { id: "passk", header: "pass^k", width: "70px", align: "right", value: (s) => s.health.consistencyPassK, hideOnMobile: true, cell: (s) => pct(s.health.consistencyPassK) },
      { id: "conf", header: "Conformance", width: "100px", align: "right", value: (s) => s.health.conformance, cell: (s) => <span className={cn(s.health.conformance < 0.75 && "text-risk")}>{pct(s.health.conformance)}</span> },
      { id: "evals", header: "Eval cases", width: "84px", align: "right", value: (s) => s.evalSuite.cases, hideOnMobile: true, cell: (s) => s.evalSuite.cases },
      { id: "updated", header: "Updated", width: "100px", value: (s) => s.updatedAt, hideOnMobile: true, cell: (s) => <span className="text-muted-foreground">{relTime(s.updatedAt)}</span> },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lookup, info],
  );
  return (
    <div>
      <PageHeader title="Skills studio and Agent Academy" description="A skill is an employee's documented capability. Eval suites run in a sandbox. Agents move from trainee to supervised to autonomous." />
      <Tabs defaultValue="skills">
        <TabsList>
          <TabsTrigger value="skills">Skills</TabsTrigger>
          <TabsTrigger value="drafts">Drafts {drafts.length > 0 && <span className="ml-1 text-muted-foreground">{drafts.length}</span>}</TabsTrigger>
          <TabsTrigger value="academy">Academy</TabsTrigger>
        </TabsList>
        <TabsContent value="skills" className="mt-3">
          <QueryView query={skills}>{() => <DataTable label="Skills" data={category === "all" ? main : main.filter((s) => categoryOf(s) === category)} toolbar={<CategoryFilter label="Filter by category" allLabel="All categories" value={category} onChange={setCategory} options={countBy(main, categoryOf)} />} columns={columns} getRowId={(s) => `${s.id}@${s.branch}`} onRowClick={(s) => router.push(`/l2/skills/${s.id}`)} initialSort={{ id: "conf", desc: false }} height="calc(100dvh - 280px)" />}</QueryView>
        </TabsContent>
        <TabsContent value="drafts" className="mt-3">
          {drafts.length === 0 ? (
            <EmptyState title="No draft skills" description="Skillify a handled conversation, or edit a skill to start one." />
          ) : (
            <ul className="grid gap-2 md:grid-cols-2">
              {drafts.map((s) => (
                <li key={`${s.id}@${s.branch}`} className="rounded-xl border bg-card p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <Link href={`/l2/skills/${s.id}`} className="font-medium hover:underline">{s.name}</Link>
                    <StatusChip tone="info">{s.origin}</StatusChip>
                  </div>
                  <Mono className="mt-1 block text-muted-foreground">{s.branch}</Mono>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>
        <TabsContent value="academy" className="mt-3">
          <QueryView query={agents}>
            {(as) => (
              <div className="grid gap-3 md:grid-cols-3">
                {(["trainee", "supervised", "autonomous"] as const).map((level) => (
                  <Section key={level} title={<span className="capitalize">{level}</span>} description={`${as.filter((a) => a.autonomy === level).length} agents`}>
                    <ul className="max-h-[50vh] space-y-1.5 overflow-auto">
                      {as
                        .filter((a) => a.autonomy === level)
                        .slice(0, 120)
                        .map((a) => (
                          <li key={a.id} className="flex items-center justify-between gap-2 text-sm">
                            <AgentChip id={a.id} />
                            <span className="text-xs tabular text-muted-foreground">{pct(a.taskSuccess)}</span>
                          </li>
                        ))}
                    </ul>
                  </Section>
                ))}
              </div>
            )}
          </QueryView>
        </TabsContent>
      </Tabs>
    </div>
  );
}

type DraftStep = { kind: SkillStep["kind"]; text: string; tool: string | null };

export function SkillEditor() {
  const { id } = useParams<{ id: string }>();
  const versions = useSkillVersions(id);
  return (
    <QueryView query={versions}>
      {(vs) => {
        const live = vs.find((s) => s.branch === "main") ?? vs[0];
        return live ? <SkillEditorForm key={`${live.id}@${live.version}@${live.branch}`} live={live} versions={vs} /> : null;
      }}
    </QueryView>
  );
}

function SkillEditorForm({ live, versions }: { live: Skill; versions: Skill[] }) {
  const { user } = useCurrentUser();
  const router = useRouter();
  const [trigger, setTrigger] = useState(live.trigger);
  const [steps, setSteps] = useState<DraftStep[]>(() => live.steps.map((s) => ({ kind: s.kind, text: s.text, tool: s.tool })));
  const save = useOp<{ skillId: string; trigger: string; steps: DraftStep[] }>("saveSkillDraft", { success: "Draft saved on a sandbox branch with a change request" });
  const dirty = trigger !== live.trigger || JSON.stringify(steps) !== JSON.stringify(live.steps.map((s) => ({ kind: s.kind, text: s.text, tool: s.tool })));
  const canEdit = !!user && user.tier !== "L3" && live.branch === "main";
  const move = (i: number, d: -1 | 1) => setSteps((s) => {
    const next = [...s];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    return next;
  });
  return (
          <div>
            <PageHeader eyebrow={<Link href="/l2/skills" className="hover:underline">Skills studio</Link>} title={`${live.name} v${live.version}`} description={<span className="inline-flex flex-wrap items-center gap-1"><Status value={live.status} /> on <Mono>{live.branch}</Mono> · DRI <PersonChip id={live.dri} /></span>} />
            <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
              <Section title="Skill definition" description={canEdit ? "Edit and save. Your change goes to a sandbox branch as a change request; main never changes directly." : "Read only."}>
                <div className="space-y-4">
                  <div>
                    <label htmlFor="trigger" className="mb-1 block text-xs font-medium">Trigger</label>
                    <Input id="trigger" value={trigger} onChange={(e) => setTrigger(e.target.value)} disabled={!canEdit} />
                  </div>
                  <div>
                    <div className="mb-1 text-xs font-medium">Steps</div>
                    <ol className="space-y-2">
                      {steps.map((s, i) => (
                        <li key={i} className="flex items-start gap-2 rounded-lg border bg-surface/50 p-2">
                          <span className="mt-2 w-5 text-center text-xs text-muted-foreground tabular">{i + 1}</span>
                          <Select value={s.kind} onValueChange={(v) => setSteps((all) => all.map((x, j) => (j === i ? { ...x, kind: v as DraftStep["kind"] } : x)))} disabled={!canEdit}>
                            <SelectTrigger size="sm" className="w-[130px] text-xs" aria-label={`Step ${i + 1} kind`}>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="retrieval">Retrieval</SelectItem>
                              <SelectItem value="judgment">Judgment</SelectItem>
                              <SelectItem value="tool">Tool call</SelectItem>
                              <SelectItem value="quality_gate">Quality gate</SelectItem>
                            </SelectContent>
                          </Select>
                          <Input value={s.text} onChange={(e) => setSteps((all) => all.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} disabled={!canEdit} aria-label={`Step ${i + 1} text`} className="flex-1" />
                          {canEdit && (
                            <div className="flex">
                              <Button size="icon-sm" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up"><ArrowUp /></Button>
                              <Button size="icon-sm" variant="ghost" disabled={i === steps.length - 1} onClick={() => move(i, 1)} aria-label="Move down"><ArrowDown /></Button>
                              <Button size="icon-sm" variant="ghost" onClick={() => setSteps((all) => all.filter((_, j) => j !== i))} aria-label="Remove step"><Trash2 /></Button>
                            </div>
                          )}
                        </li>
                      ))}
                    </ol>
                    {canEdit && (
                      <Button size="sm" variant="ghost" className="mt-2" onClick={() => setSteps((s) => [...s, { kind: "judgment", text: "New step", tool: null }])}>
                        <Plus /> Add step
                      </Button>
                    )}
                  </div>
                  <KeyValue
                    items={[
                      ["Inputs", live.inputs.join(", ")],
                      ["Tools", live.tools.map((t) => t.replace("tool:", "")).join(", ")],
                      ["Governing policies", live.policies.map((p) => <Link key={p} href={`/l2/policies/${p}`} className="mr-2 hover:underline">{p}</Link>)],
                      ["Required capabilities", live.requiredCapabilities.map((c) => <Mono key={c} className="mr-1 rounded bg-muted px-1">{c}</Mono>)],
                      ["Outputs", live.outputs.join(", ")],
                      ["Template fields", live.templateFields.map((f) => <Mono key={f} className="mr-1">{f}</Mono>)],
                    ]}
                  />
                  {canEdit && (
                    <Button
                      disabled={!dirty || save.isPending}
                      onClick={() => save.mutate({ skillId: live.id, trigger, steps }, { onSuccess: (cr) => router.push(`/l2/versioning/${(cr as { id: string }).id}`) })}
                    >
                      <Save /> Save as draft on a sandbox branch
                    </Button>
                  )}
                </div>
              </Section>
              <div className="space-y-4">
                <Section title="Skill health">
                  <HealthBars s={live} />
                </Section>
                <Section title="Eval suite" description="Runs in a sandbox against recorded cases">
                  <KeyValue items={[["Suite", <Mono key="s">{live.evalSuite.id}</Mono>], ["Cases", live.evalSuite.cases], ["Pass rate", pct(live.evalSuite.passRate)]]} />
                </Section>
                <Section title="Agents using it">
                  <ul className="space-y-1 text-sm">{live.agentIds.map((a) => <li key={a}><AgentChip id={a} /></li>)}</ul>
                </Section>
                {versions.filter((v) => v.branch !== "main").length > 0 && (
                  <Section title="Drafts of this skill">
                    <ul className="space-y-1 text-xs">
                      {versions.filter((v) => v.branch !== "main").map((v) => <li key={v.branch}><Mono>{v.branch}</Mono> · {v.origin}</li>)}
                    </ul>
                  </Section>
                )}
              </div>
            </div>
          </div>
  );
}
