"use client";

import { AlertOctagon, AlertTriangle, ChevronDown, Info, MessageSquarePlus, Network, Share2 } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { FieldValue, Revision, StudioItem, WorkflowDetail, WorkflowSummary } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PersonChip } from "@/components/brain/names";
import { CritBadge, Mono, Status, StatusChip } from "@/components/brain/primitives";
import { useStudioActivity, useStudioHealth, useStudioHistory, useStudioPending } from "@/lib/api/hooks";
import { relTime } from "@/lib/format";
import { FIELD_SPECS, KIND_LABEL, KIND_PLURAL, MEMBER_ORDER, describeCron, fieldLabel, formatValue, isParam, paramName, refsOf } from "@/lib/studio/spec";
import { cn } from "@/lib/utils";
import { KindIcon } from "./cards";
import type { Focus } from "./state";

type Props = {
  detail: WorkflowDetail;
  summaries: WorkflowSummary[];
  focus: Focus;
  now: number;
  onFocus: (f: Focus) => void;
  onAsk: (prompt: string) => void;
  onSwitch: (workflowId: string) => void;
  onShowOnDiagram: (id: string) => void;
};

function show(detail: WorkflowDetail, kind: StudioItem["kind"], key: string, v: FieldValue | undefined): string {
  if (v === undefined || v === "" || (Array.isArray(v) && !v.length)) return "—";
  const spec = FIELD_SPECS[kind].find((f) => f.key === key);
  if (spec && (spec.type === "refs" || spec.type === "ref")) return (Array.isArray(v) ? v : [String(v)]).map((id) => detail.items.find((i) => i.id === id)?.name ?? id).join(", ");
  if (key === "cron") return `${describeCron(String(v))} · ${v}`;
  return formatValue(v, isParam(key) ? paramName(key) : key);
}

export function DetailsPanel(props: Props) {
  const { detail, focus } = props;
  const item = focus && focus.kind !== "workflow" ? detail.items.find((i) => i.id === focus.id) ?? null : null;
  const [tab, setTab] = useState("details");
  return (
    <aside className="flex h-full min-h-0 flex-col border-l bg-card" aria-label="Details">
      <div className="border-b px-3 py-2.5">
        {item ? (
          <>
            <button type="button" className="mb-1 text-[11px] text-muted-foreground hover:underline" onClick={() => props.onFocus({ kind: "workflow", id: detail.workflow.id })}>
              ← {detail.workflow.name}
            </button>
            <div className="flex items-start gap-2">
              <KindIcon kind={item.kind} className="mt-0.5 size-4" />
              <div className="min-w-0 flex-1">
                <h2 className="text-sm font-semibold leading-tight">{item.name}</h2>
                <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
                  <span>{KIND_LABEL[item.kind]}</span>·<span>v{item.version}</span>·<Status value={item.status} />
                  {item.kind === "tool" && <StatusChip tone="info">shared</StatusChip>}
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex items-start gap-2">
            <KindIcon kind="workflow" className="mt-0.5 size-4" />
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-semibold leading-tight">{detail.workflow.name}</h2>
              <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
                <span>Workflow · v{detail.workflow.version}</span>
                <Status value={detail.workflow.status} />
                <CritBadge level={detail.workflow.criticality} />
              </div>
            </div>
          </div>
        )}
      </div>
      <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col gap-0">
        <TabsList className="mx-3 mt-2 grid w-auto grid-cols-3">
          <TabsTrigger value="details" className="text-xs">Details</TabsTrigger>
          <TabsTrigger value="history" className="text-xs">Versions</TabsTrigger>
          <TabsTrigger value="related" className="text-xs">Related</TabsTrigger>
        </TabsList>
        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3 pt-2">
          <TabsContent value="details">{item ? <ItemDetails {...props} item={item} /> : <WorkflowDetails {...props} />}</TabsContent>
          <TabsContent value="history">
            <History targetId={item?.id ?? detail.workflow.id} current={item?.version ?? detail.workflow.version} kind={item?.kind ?? null} detail={detail} now={props.now} />
            {!item && <Activity {...props} />}
          </TabsContent>
          <TabsContent value="related">
            <Related {...props} item={item} />
          </TabsContent>
        </div>
      </Tabs>
    </aside>
  );
}

function Findings({ workflowId, onlyId }: { workflowId: string; onlyId?: string }) {
  const health = useStudioHealth(workflowId);
  const list = (health.data?.findings ?? []).filter((f) => f.severity !== "info" && (!onlyId || f.ref?.id === onlyId));
  if (!list.length) return null;
  return (
    <div className="space-y-1">
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Health</div>
      <ul className="space-y-1">
        {list.slice(0, 8).map((f, i) => (
          <li key={i} className={cn("flex gap-1.5 rounded-lg px-2 py-1 text-xs", f.severity === "break" ? "bg-risk/8" : "bg-warn/10")}>
            {f.severity === "break" ? <AlertOctagon className="mt-0.5 size-3.5 shrink-0 text-risk" aria-label="break" /> : <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warn-fg" aria-label="warning" />}
            <span>{f.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{children}</div>;
}

function ItemDetails({ item, detail, onAsk, onShowOnDiagram }: Props & { item: StudioItem }) {
  const fields = [...FIELD_SPECS[item.kind].map((s) => s.key), ...Object.keys(item.fields).filter(isParam)];
  return (
    <div className="space-y-3">
      <p className="text-xs leading-relaxed">{item.description || <span className="text-muted-foreground">No description yet.</span>}</p>
      {item.topics.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {item.topics.map((t) => (
            <span key={t} className="rounded-full bg-muted px-2 py-0.5 text-[11px]">#{t}</span>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        <Button size="xs" variant="outline" onClick={() => onAsk(`Change … of ${item.name}`)}>
          <MessageSquarePlus /> Edit in chat
        </Button>
        <Button size="xs" variant="ghost" onClick={() => onShowOnDiagram(item.id)}>
          <Network /> Show on diagram
        </Button>
      </div>
      <Findings workflowId={detail.workflow.id} onlyId={item.id} />
      <div className="space-y-1.5">
        <Label>Settings</Label>
        <dl className="space-y-1.5 text-xs">
          {fields.map((k) => (
            <div key={k} className="grid grid-cols-[minmax(84px,40%)_1fr] gap-2">
              <dt className="text-muted-foreground">{fieldLabel(item.kind, k)}</dt>
              <dd className="min-w-0 break-words">{k === "steps" && Array.isArray(item.fields.steps) ? <ol className="list-decimal space-y-0.5 pl-4">{(item.fields.steps as string[]).map((s, i) => <li key={i}>{s}</li>)}</ol> : show(detail, item.kind, k, item.fields[k])}</dd>
            </div>
          ))}
          <div className="grid grid-cols-[minmax(84px,40%)_1fr] gap-2">
            <dt className="text-muted-foreground">DRI</dt>
            <dd><PersonChip id={item.dri} /></dd>
          </div>
          <div className="grid grid-cols-[minmax(84px,40%)_1fr] gap-2">
            <dt className="text-muted-foreground">Id</dt>
            <dd><Mono className="break-all text-[11px] text-muted-foreground">{item.id}</Mono></dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

function WorkflowDetails({ detail, onFocus, onAsk, summaries }: Props) {
  const wf = detail.workflow;
  const summary = summaries.find((s) => s.id === wf.id);
  const pending = useStudioPending();
  const open = (pending.data ?? []).filter((p) => p.workflowId === wf.id && p.status === "awaiting_approval");
  return (
    <div className="space-y-3">
      <p className="text-xs leading-relaxed">{wf.description}</p>
      <div className="flex flex-wrap gap-1">
        {wf.topics.map((t) => (
          <span key={t} className="rounded-full bg-muted px-2 py-0.5 text-[11px]">#{t}</span>
        ))}
      </div>
      <dl className="space-y-1.5 text-xs">
        <div className="flex items-center justify-between gap-2"><dt className="text-muted-foreground">DRI</dt><dd><PersonChip id={wf.dri} /></dd></div>
        {wf.editors.length > 0 && <div className="flex items-start justify-between gap-2"><dt className="text-muted-foreground">Editors</dt><dd className="flex flex-col items-end gap-1">{wf.editors.map((e) => <PersonChip key={e} id={e} />)}</dd></div>}
        {summary && <div className="flex items-center justify-between gap-2"><dt className="text-muted-foreground">Health</dt><dd>{summary.health.breaks ? <StatusChip tone="risk">{summary.health.breaks} break{summary.health.breaks === 1 ? "" : "s"}</StatusChip> : <StatusChip tone="ok">no breaks</StatusChip>} {summary.health.warnings > 0 && <StatusChip tone="warn">{summary.health.warnings} warning{summary.health.warnings === 1 ? "" : "s"}</StatusChip>}</dd></div>}
      </dl>
      <Button size="xs" variant="outline" onClick={() => onAsk(`Change … of the ${wf.name} workflow`)}>
        <MessageSquarePlus /> Edit in chat
      </Button>
      {open.length > 0 && (
        <div className="space-y-1">
          <Label>Waiting for approval</Label>
          <ul className="space-y-1">
            {open.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-2 rounded-lg bg-surface px-2 py-1 text-xs">
                <Link href={`/l2/versioning/${p.changeRequestId}`} className="truncate hover:underline">{p.title}</Link>
                <CritBadge level={p.criticality} />
              </li>
            ))}
          </ul>
        </div>
      )}
      <Findings workflowId={wf.id} />
      <div className="space-y-2">
        <Label>Parts</Label>
        {MEMBER_ORDER.map((k) => {
          const list = detail.items.filter((i) => i.kind === k);
          if (!list.length) return null;
          return (
            <div key={k}>
              <div className="mb-0.5 flex items-center gap-1.5 text-[11px] font-medium"><KindIcon kind={k} className="size-3" />{KIND_PLURAL[k]} <span className="text-muted-foreground">{list.length}</span></div>
              <ul className="space-y-0.5">
                {list.map((i) => (
                  <li key={i.id}>
                    <button type="button" className="min-h-6 w-full truncate rounded px-1.5 py-0.5 text-left text-xs hover:bg-accent" onClick={() => onFocus({ kind: i.kind, id: i.id })}>
                      {i.name} {i.status !== "active" && <span className="text-muted-foreground">({i.status})</span>}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function snapshotDiff(prev: Revision | undefined, cur: Revision, kind: StudioItem["kind"] | null): string[] {
  if (!cur.snapshot) return ["Deleted"];
  if (!prev?.snapshot) return [];
  const a = prev.snapshot;
  const b = cur.snapshot;
  const out: string[] = [];
  for (const k of ["name", "description", "status"] as const) if (a[k] !== b[k]) out.push(`${k}: ${a[k]} → ${b[k]}`);
  if (a.topics.join() !== b.topics.join()) out.push(`topics: ${a.topics.join(", ")} → ${b.topics.join(", ")}`);
  for (const k of new Set([...Object.keys(a.fields), ...Object.keys(b.fields)])) {
    if (JSON.stringify(a.fields[k]) !== JSON.stringify(b.fields[k])) out.push(`${kind ? fieldLabel(kind, k) : k}: ${formatValue(a.fields[k], paramName(k))} → ${formatValue(b.fields[k], paramName(k))}`);
  }
  return out;
}

function History({ targetId, current, kind, now }: { targetId: string; current: number; kind: StudioItem["kind"] | null; detail: WorkflowDetail; now: number }) {
  const history = useStudioHistory(targetId);
  const [open, setOpen] = useState<string | null>(null);
  const list = history.data ?? [];
  if (history.isLoading) return <p className="text-xs text-muted-foreground">Loading versions…</p>;
  if (!list.length) return <p className="text-xs text-muted-foreground">No versions recorded yet.</p>;
  return (
    <ol className="relative space-y-2 border-l pl-3">
      {list.map((r, i) => {
        const prev = list[i + 1];
        const lines = snapshotDiff(prev, r, kind);
        return (
          <li key={r.id} className="relative">
            <span className={cn("absolute -left-[17px] top-1.5 size-2 rounded-full ring-2 ring-card", r.version === current ? "bg-primary" : "bg-muted-foreground/40")} aria-hidden />
            <button type="button" className="w-full text-left" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
              <div className="flex items-center gap-1.5 text-xs">
                <span className="font-semibold tabular">v{r.version}</span>
                {r.version === current && <StatusChip tone="info" className="h-4 px-1.5 text-[10px]">current</StatusChip>}
                {r.verdict && <StatusChip tone={r.verdict === "breaking" ? "risk" : r.verdict === "moderate" ? "warn" : "ok"} className="h-4 px-1.5 text-[10px]">{r.verdict}</StatusChip>}
                <span className="ml-auto text-[10px] text-muted-foreground">{relTime(r.at, now)}</span>
                {lines.length > 0 && <ChevronDown className={cn("size-3 text-muted-foreground transition-transform", open === r.id && "rotate-180")} aria-hidden />}
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">{r.summary}</div>
            </button>
            {open === r.id && lines.length > 0 && (
              <ul className="mt-1 space-y-0.5 rounded-lg bg-surface p-2 text-[11px]">
                {lines.map((l, j) => <li key={j} className="break-words">{l}</li>)}
              </ul>
            )}
            <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
              <PersonChip id={r.by} className="text-[10px]" />
              {r.changeRequestId && <Link href={`/l2/versioning/${r.changeRequestId}`} className="hover:underline">· {r.changeRequestId}</Link>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Activity({ detail, now, onFocus }: Props) {
  const activity = useStudioActivity(detail.workflow.id);
  const list = (activity.data ?? []).filter((r) => r.targetId !== detail.workflow.id).slice(0, 10);
  if (!list.length) return null;
  return (
    <div className="mt-4 space-y-1">
      <Label>Recent changes to its parts</Label>
      <ul className="space-y-1">
        {list.map((r) => (
          <li key={r.id}>
            <button type="button" className="min-h-6 flex w-full items-start gap-1.5 rounded px-1 py-0.5 text-left text-xs hover:bg-accent" onClick={() => r.targetKind !== "workflow" && onFocus({ kind: r.targetKind, id: r.targetId })}>
              <KindIcon kind={r.targetKind} className="mt-0.5 size-3" />
              <span className="min-w-0 flex-1"><span className="font-medium">{r.snapshot?.name ?? r.targetId}</span> v{r.version} · <span className="text-muted-foreground">{r.summary}</span></span>
              <span className="shrink-0 text-[10px] text-muted-foreground">{relTime(r.at, now)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Related({ detail, summaries, item, onFocus, onSwitch }: Props & { item: StudioItem | null }) {
  const { inWorkflow, others } = useMemo(() => {
    const byId = new Map(detail.items.map((i) => [i.id, i]));
    const usage = new Map(detail.sharedToolUse.map((s) => [s.toolId, s.workflows]));
    if (item) {
      const out = refsOf(item.kind, item.fields).map((r) => ({ it: byId.get(r.id), how: `${r.rel}` })).filter((x): x is { it: StudioItem; how: string } => !!x.it);
      const back = detail.items.flatMap((i) => refsOf(i.kind, i.fields).filter((r) => r.id === item.id).map((r) => ({ it: i, how: `${r.rel} this` })));
      const tools = item.kind === "tool" ? [item.id] : refsOf(item.kind, item.fields).filter((r) => r.ref === "tool").map((r) => r.id);
      const wfs = new Map<string, { id: string; name: string; via: string[] }>();
      for (const t of tools) for (const w of usage.get(t) ?? []) if (w.id !== detail.workflow.id) wfs.set(w.id, { ...w, via: [...(wfs.get(w.id)?.via ?? []), byId.get(t)?.name ?? t] });
      return { inWorkflow: [...out, ...back], others: [...wfs.values()] };
    }
    const wfs = new Map<string, { id: string; name: string; via: string[] }>();
    for (const s of detail.sharedToolUse) for (const w of s.workflows) if (w.id !== detail.workflow.id) wfs.set(w.id, { ...w, via: [...(wfs.get(w.id)?.via ?? []), byId.get(s.toolId)?.name ?? s.toolId] });
    for (const s of summaries) if (s.id !== detail.workflow.id && s.topics.some((t) => detail.workflow.topics.includes(t)) && !wfs.has(s.id)) wfs.set(s.id, { id: s.id, name: s.name, via: [`topic ${s.topics.find((t) => detail.workflow.topics.includes(t))}`] });
    return { inWorkflow: [], others: [...wfs.values()] };
  }, [detail, item, summaries]);
  return (
    <div className="space-y-3">
      {item && (
        <div className="space-y-1">
          <Label>Connected in this workflow</Label>
          {inWorkflow.length === 0 ? <p className="text-xs text-muted-foreground">Nothing connects to it.</p> : (
            <ul className="space-y-0.5">
              {inWorkflow.map((x, i) => (
                <li key={`${x.it.id}${i}`}>
                  <button type="button" className="min-h-6 flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-xs hover:bg-accent" onClick={() => onFocus({ kind: x.it.kind, id: x.it.id })}>
                    <KindIcon kind={x.it.kind} className="size-3" />
                    <span className="truncate">{x.it.name}</span>
                    <span className="ml-auto shrink-0 text-[10px] text-muted-foreground">{x.how}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="space-y-1">
        <Label>Related workflows</Label>
        {others.length === 0 ? <p className="text-xs text-muted-foreground">{item ? "No other workflow depends on this." : "No other workflow shares a tool or topic with this one."}</p> : (
          <ul className="space-y-1">
            {others.map((w) => (
              <li key={w.id}>
                <button type="button" className="min-h-6 w-full rounded-lg border px-2 py-1.5 text-left text-xs hover:bg-accent" onClick={() => onSwitch(w.id)}>
                  <div className="flex items-center gap-1.5 font-medium"><Share2 className="size-3 text-muted-foreground" aria-hidden />{w.name}</div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">via {[...new Set(w.via)].join(", ")}</div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="flex gap-1.5 text-[11px] text-muted-foreground"><Info className="mt-0.5 size-3 shrink-0" aria-hidden />Only tools are shared between workflows. Everything else belongs to one workflow, so its edits stay inside it.</p>
    </div>
  );
}

