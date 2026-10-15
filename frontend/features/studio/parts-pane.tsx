"use client";

import { ArrowLeft, ArrowRight, Check, ChevronDown, Info, LayoutList, MessageSquarePlus, Network, Pencil, Plus, History } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { FieldChange, Finding, MemberKind, Proposal, StoryDraft, StudioItem, WorkflowDetail, WorkflowSummary } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useStudioHealth, useStudioPending } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import type { Highlight } from "@/lib/studio/graph";
import { KIND_LABEL, KIND_PLURAL, TOOL_LEVEL_LABEL, describeCron, fieldLabel, formatValue, isParam, paramName, visibleSpecs } from "@/lib/studio/spec";
import { buildPrompt, coverageOf } from "@/lib/studio/story";
import { cn } from "@/lib/utils";
import { KindIcon, kindColor } from "./cards";
import { DetailsPanel } from "./details-panel";
import { ItemForm } from "./parts";
import { StoryView } from "./story-card";
import type { ChatMessage, Focus } from "./state";
import { STEPS, stepOf, type StepKey } from "./steps";

export type PaneMode = "parts" | "diagram";

type PartState = "changing" | "fix" | "waiting" | "done" | null;

type Props = {
  detail: WorkflowDetail;
  summaries: WorkflowSummary[];
  thread: ChatMessage[];
  focus: Focus;
  step: StepKey;
  mode: PaneMode;
  now: number;
  diagram: ReactNode;
  onStep: (s: StepKey) => void;
  onMode: (m: PaneMode) => void;
  onFocus: (f: Focus) => void;
  onAsk: (prompt: string) => void;
  onSwitch: (workflowId: string) => void;
  onShowDiagram: (h: Highlight) => void;
};

/** The latest proposal the chat made that nobody has confirmed yet: the part being filled right now. */
export function activeProposal(thread: ChatMessage[]): Proposal | null {
  for (let i = thread.length - 1; i >= 0; i--) {
    const m = thread[i];
    if (m.role === "assistant") return m.reply.proposal && !m.applied ? m.reply.proposal : null;
  }
  return null;
}

/** The story the chat drafted last and is waiting on the person to confirm. */
function openDraft(thread: ChatMessage[]): StoryDraft | null {
  for (let i = thread.length - 1; i >= 0; i--) {
    const m = thread[i];
    if (m.role === "assistant") return m.reply.story;
  }
  return null;
}

/** One line that says what a part does, so the card needs no form to be understood. */
function summaryOf(it: StudioItem): string {
  const f = it.fields;
  const parts: string[] = [];
  if (it.kind === "sensor") parts.push(String(f.source ?? ""), String(f.sensorKind ?? ""));
  if (it.kind === "scheduler") parts.push(f.cron ? describeCron(String(f.cron)) : "", f.enabled === false ? "off" : "");
  if (it.kind === "agent") parts.push(String(f.autonomy ?? ""), String(f.model ?? ""));
  if (it.kind === "skill") parts.push(String(f.trigger ?? ""));
  if (it.kind === "policy") parts.push(String(f.statement ?? ""));
  if (it.kind === "tool") parts.push(TOOL_LEVEL_LABEL[String(f.level ?? "prebuilt")] ?? "", String(f.sideEffect ?? ""));
  if (it.kind === "template") parts.push(String(f.cadence ?? ""));
  if (it.kind === "loop") parts.push(String(f.reviewCadence ?? ""), String(f.gate ?? ""));
  const line = parts.filter(Boolean).join(" · ");
  return line || it.description || "No details yet";
}

export function PartsPane(props: Props) {
  const { detail, thread, focus, step, mode } = props;
  const { user } = useCurrentUser();
  const readOnly = user?.tier === "L3";
  const health = useStudioHealth(detail.workflow.id);
  const pending = useStudioPending();
  const [sheet, setSheet] = useState<Focus | "closed">("closed");
  const [editing, setEditing] = useState<string | null>(null);

  const proposal = activeProposal(thread);
  const findings = useMemo(() => {
    const m = new Map<string, Finding[]>();
    for (const f of health.data?.findings ?? []) if (f.ref && f.severity !== "info") m.set(f.ref.id, [...(m.get(f.ref.id) ?? []), f]);
    return m;
  }, [health.data]);
  const waiting = useMemo(() => new Set((pending.data ?? []).filter((p) => p.workflowId === detail.workflow.id && p.status === "awaiting_approval").map((p) => p.input.targetId).filter(Boolean)), [pending.data, detail.workflow.id]);
  const done = useMemo(() => new Set(thread.flatMap((m) => (m.role === "assistant" && m.applied?.status === "applied" ? [m.applied.targetId] : []))), [thread]);

  const stateOf = (id: string): PartState => {
    if (proposal && proposal.input.intent !== "create" && proposal.input.targetId === id) return "changing";
    if (findings.has(id)) return "fix";
    if (waiting.has(id)) return "waiting";
    if (done.has(id)) return "done";
    return null;
  };

  const current = STEPS.find((s) => s.key === step) ?? STEPS[0];
  const index = STEPS.indexOf(current);
  const draft = openDraft(thread);
  const proposalStep = draft || proposal?.input.patch.story ? "story" : proposal && proposal.input.kind !== "workflow" ? stepOf(proposal.input.kind) : null;

  return (
    <section className="flex h-full min-h-0 flex-col bg-background" aria-label="Workflow parts">
      <header className="flex items-center gap-3 border-b px-5 py-3">
        {mode === "parts" ? (
          <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" aria-label="Steps">
            {STEPS.map((s, i) => {
              const items = detail.items.filter((x) => s.kinds.includes(x.kind));
              const busy = proposalStep === s.key;
              const fix = s.key === "story" ? !detail.workflow.story : items.some((x) => findings.has(x.id));
              const on = s.key === current.key;
              return (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => props.onStep(s.key)}
                  aria-current={on ? "step" : undefined}
                  className={cn("flex shrink-0 items-center gap-2 rounded-full px-3 py-1.5 text-xs transition-colors", on ? "bg-accent font-medium text-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground")}
                >
                  <span className={cn("grid size-5 place-items-center rounded-full text-[10px] tabular-nums", on ? "bg-foreground text-background" : "bg-muted")}>{i + 1}</span>
                  <span className={cn(!on && "max-xl:hidden")}>{s.label}</span>
                  {(busy || fix) && <span className={cn("size-1.5 rounded-full", busy ? "animate-pulse bg-primary" : "bg-warn")} aria-label={busy ? "changing now" : "needs a fix"} />}
                </button>
              );
            })}
          </nav>
        ) : (
          <p className="min-w-0 flex-1 truncate text-sm font-medium">Map of {detail.workflow.name}</p>
        )}
        <ToggleGroup type="single" value={mode} onValueChange={(v) => v && props.onMode(v as PaneMode)} variant="outline" size="sm" aria-label="View">
          <ToggleGroupItem value="parts" aria-label="Parts"><LayoutList /></ToggleGroupItem>
          <ToggleGroupItem value="diagram" aria-label="Diagram"><Network /></ToggleGroupItem>
        </ToggleGroup>
        <Button size="icon-sm" variant="ghost" onClick={() => setSheet({ kind: "workflow", id: detail.workflow.id })} aria-label="About this workflow">
          <Info />
        </Button>
      </header>

      {mode === "diagram" ? (
        <div className="min-h-0 flex-1 p-4">{props.diagram}</div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div key={current.key} className="mx-auto max-w-3xl space-y-8 px-5 py-8 animate-in fade-in duration-300 sm:px-8">
            <div>
              <p className="text-xs text-muted-foreground">Step {index + 1} of {STEPS.length}</p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight">{current.label}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{current.hint}</p>
            </div>

            {current.key === "story" && (
              <StoryStep
                detail={detail}
                draft={draft ?? (proposal?.input.kind === "workflow" && proposal.input.patch.story ? { workflowId: proposal.input.intent === "create" ? null : proposal.input.targetId, name: proposal.input.patch.name ?? detail.workflow.name, story: proposal.input.patch.story } : null)}
                readOnly={readOnly}
                onAsk={props.onAsk}
              />
            )}

            {current.kinds.map((k) => {
              const list = detail.items.filter((i) => i.kind === k);
              const draft = proposal && proposal.input.intent === "create" && proposal.input.kind === k ? proposal : null;
              return (
                <div key={k} className="space-y-3">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-medium">{KIND_PLURAL[k]}</h3>
                    <span className="text-xs text-muted-foreground tabular-nums">{list.length}</span>
                    {!readOnly && (
                      <Button size="xs" variant="ghost" className="ml-auto text-muted-foreground" onClick={() => props.onAsk(`Add a ${KIND_LABEL[k].toLowerCase()} that …`)}>
                        <Plus /> Add
                      </Button>
                    )}
                  </div>
                  {draft && <DraftCard kind={k} proposal={draft} />}
                  {list.length === 0 && !draft && <p className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">No {KIND_PLURAL[k].toLowerCase()} yet</p>}
                  <div className="space-y-3">
                    {list.map((it) => (
                      <PartCard
                        key={it.id}
                        item={it}
                        detail={detail}
                        state={stateOf(it.id)}
                        changes={proposal?.input.targetId === it.id ? proposal.changes : []}
                        findings={findings.get(it.id) ?? []}
                        open={focus?.id === it.id}
                        editing={editing === it.id}
                        readOnly={readOnly}
                        onToggle={() => { setEditing(null); props.onFocus(focus?.id === it.id ? null : { kind: it.kind, id: it.id }); }}
                        onEdit={() => setEditing(editing === it.id ? null : it.id)}
                        onAsk={() => { props.onFocus({ kind: it.kind, id: it.id }); props.onAsk(`Change … of ${it.name}`); }}
                        onMore={() => setSheet({ kind: it.kind, id: it.id })}
                        onShowDiagram={props.onShowDiagram}
                      />
                    ))}
                  </div>
                </div>
              );
            })}

            <div className="flex items-center justify-between border-t pt-6">
              {index > 0 ? (
                <Button variant="ghost" size="sm" onClick={() => props.onStep(STEPS[index - 1].key)}><ArrowLeft /> {STEPS[index - 1].label}</Button>
              ) : <span />}
              {index < STEPS.length - 1 && (
                <Button variant="outline" size="sm" onClick={() => props.onStep(STEPS[index + 1].key)}>{STEPS[index + 1].label} <ArrowRight /></Button>
              )}
            </div>
          </div>
        </div>
      )}

      <Sheet open={sheet !== "closed"} onOpenChange={(o) => !o && setSheet("closed")}>
        <SheetContent side="right" className="w-full p-0 sm:max-w-md">
          <SheetTitle className="sr-only">Details</SheetTitle>
          {sheet !== "closed" && (
            <DetailsPanel
              detail={detail}
              summaries={props.summaries}
              focus={sheet}
              now={props.now}
              onFocus={(f) => setSheet(f)}
              onAsk={(p) => { setSheet("closed"); props.onAsk(p); }}
              onSwitch={(id) => { setSheet("closed"); props.onSwitch(id); }}
              onShowOnDiagram={(id) => { setSheet("closed"); props.onShowDiagram({ target: id, affected: new Set(), broken: new Set() }); }}
            />
          )}
        </SheetContent>
      </Sheet>
    </section>
  );
}

/** The problem and its cases. A story the chat is drafting shows here while it is being confirmed. */
function StoryStep({ detail, draft, readOnly, onAsk }: { detail: WorkflowDetail; draft: StoryDraft | null; readOnly: boolean; onAsk: (p: string) => void }) {
  const live = draft?.story ?? null;
  const story = live ?? detail.workflow.story;
  const forOther = draft && draft.workflowId !== detail.workflow.id;
  if (!story) {
    return (
      <div className="rounded-xl border border-dashed px-6 py-10 text-center">
        <p className="text-base font-medium">No story yet</p>
        <p className="mt-1 text-sm text-muted-foreground">Describe the problem this workflow solves. The chat turns it into cases.</p>
        {!readOnly && <Button className="mt-5" variant="outline" onClick={() => onAsk("The problem is …")}>Describe the problem</Button>}
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {live && (
        <div className="flex items-center gap-2 text-sm">
          <StateChip state="changing" />
          <span className="text-muted-foreground">{forOther ? `New workflow: ${draft!.name}. Confirm the cases in the chat.` : "Confirm these cases in the chat."}</span>
        </div>
      )}
      <StoryView
        key={live ? "live" : "saved"}
        story={story}
        live={!!live}
        coverageFor={forOther ? undefined : (sc) => coverageOf(sc, detail.items)}
        onBuild={readOnly || live ? undefined : (sc) => onAsk(buildPrompt(sc))}
      />
    </div>
  );
}

function StateChip({ state }: { state: PartState }) {
  if (!state) return null;
  const look = {
    changing: { text: "Changing", cls: "bg-primary/10 text-primary", dot: "animate-pulse bg-primary" },
    fix: { text: "Needs fix", cls: "bg-warn/15 text-warn-fg", dot: "bg-warn" },
    waiting: { text: "Waiting approval", cls: "bg-muted text-muted-foreground", dot: "bg-muted-foreground/60" },
    done: { text: "Updated", cls: "bg-ok/10 text-ok", dot: "" },
  }[state];
  return (
    <span className={cn("inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[11px] font-medium", look.cls)}>
      {state === "done" ? <Check className="size-3" aria-hidden /> : <span className={cn("size-1.5 rounded-full", look.dot)} aria-hidden />}
      {look.text}
    </span>
  );
}

function PartIcon({ kind }: { kind: MemberKind }) {
  return (
    <span className="grid size-9 shrink-0 place-items-center rounded-lg" style={{ background: `color-mix(in oklab, ${kindColor(kind)} 12%, transparent)` }}>
      <KindIcon kind={kind} className="size-4" />
    </span>
  );
}

/** Field changes from the open proposal, appearing one by one as if being written in. */
function ChangeList({ changes, create }: { changes: FieldChange[]; create?: boolean }) {
  const list = changes.filter((c) => !create || c.after).slice(0, 8);
  if (!list.length) return null;
  return (
    <ul className="space-y-2 border-t px-4 py-4 text-sm">
      {list.map((c, i) => (
        <li key={c.field} className="grid grid-cols-[minmax(96px,30%)_1fr] gap-3 animate-in fade-in slide-in-from-left-1 fill-mode-both duration-500" style={{ animationDelay: `${i * 90}ms` }}>
          <span className="text-xs text-muted-foreground">{c.label}</span>
          <span className="min-w-0 break-words">
            {!create && c.before && <span className="mr-1.5 text-muted-foreground line-through">{c.before}</span>}
            <span className="font-medium">{c.after ?? "removed"}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Brings the part being filled right now into view. */
function useScrollWhen(on: boolean, key: unknown) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (on) ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [on, key]);
  return ref;
}

function DraftCard({ kind, proposal }: { kind: MemberKind; proposal: Proposal }) {
  const ref = useScrollWhen(true, proposal);
  return (
    <div ref={ref} className="scroll-m-6 overflow-hidden rounded-xl border border-primary/40 bg-card ring-2 ring-primary/20 animate-in fade-in zoom-in-95 duration-300">
      <div className="flex items-center gap-3 p-4">
        <PartIcon kind={kind} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{proposal.input.patch.name ?? `New ${KIND_LABEL[kind].toLowerCase()}`}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">New {KIND_LABEL[kind].toLowerCase()} · confirm it in the chat</p>
        </div>
        <StateChip state="changing" />
      </div>
      <ChangeList changes={proposal.changes} create />
    </div>
  );
}

function PartCard({ item, detail, state, changes, findings, open, editing, readOnly, onToggle, onEdit, onAsk, onMore, onShowDiagram }: {
  item: StudioItem; detail: WorkflowDetail; state: PartState; changes: FieldChange[]; findings: Finding[]; open: boolean; editing: boolean; readOnly: boolean;
  onToggle: () => void; onEdit: () => void; onAsk: () => void; onMore: () => void; onShowDiagram: (h: Highlight) => void;
}) {
  const ref = useScrollWhen(state === "changing", changes);
  return (
    <div ref={ref} className={cn("scroll-m-6 overflow-hidden rounded-xl border bg-card transition-[box-shadow,border-color] duration-300", state === "changing" && "border-primary/40 ring-2 ring-primary/20", open && state !== "changing" && "border-foreground/15 shadow-sm")} data-part={item.id}>
      <button type="button" onClick={onToggle} className="flex w-full items-center gap-3 p-4 text-left hover:bg-accent/30" aria-expanded={open}>
        <PartIcon kind={item.kind} />
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 text-sm font-medium">
            <span className="truncate">{item.name}</span>
            {item.status !== "active" && <span className="shrink-0 text-xs font-normal text-muted-foreground">{item.status}</span>}
          </p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{summaryOf(item)}</p>
        </div>
        <StateChip state={state} />
        <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} aria-hidden />
      </button>

      {state === "changing" && <ChangeList changes={changes} />}

      {open && !editing && (
        <div className="space-y-5 border-t px-4 py-5 animate-in fade-in duration-200">
          {findings.length > 0 && (
            <ul className="space-y-2">
              {findings.map((f, i) => (
                <li key={i} className={cn("rounded-lg px-3 py-2 text-xs leading-relaxed", f.severity === "break" ? "bg-risk/8 text-foreground" : "bg-warn/10")}>{f.text}</li>
              ))}
            </ul>
          )}
          <Fields item={item} detail={detail} />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={onAsk}><MessageSquarePlus /> Ask in chat</Button>
            {!readOnly && <Button size="sm" variant="ghost" onClick={onEdit}><Pencil /> Edit</Button>}
            <Button size="sm" variant="ghost" className="ml-auto text-muted-foreground" onClick={onMore}><History /> History & links</Button>
          </div>
        </div>
      )}

      {open && editing && (
        <div className="border-t px-4 py-5">
          <ItemForm key={`${item.id}@${item.version}`} kind={item.kind} item={item} detail={detail} onShowDiagram={onShowDiagram} onDone={onEdit} onCancel={onEdit} />
        </div>
      )}
    </div>
  );
}

/** The part's settings, a few at a time. Empty ones stay hidden until asked for. */
function Fields({ item, detail }: { item: StudioItem; detail: WorkflowDetail }) {
  const [all, setAll] = useState(false);
  const names = new Map(detail.items.map((i) => [i.id, i.name]));
  const rows = [
    ...visibleSpecs(item.kind, item.fields).filter((s) => s.key !== "code").map((s) => {
      const v = item.fields[s.key];
      let text = "";
      if (s.type === "ref" || s.type === "refs") text = (Array.isArray(v) ? v : v ? [String(v)] : []).map((id) => names.get(id) ?? id).join(", ");
      else if (s.key === "cron" && v) text = describeCron(String(v));
      else if (s.key === "level") text = TOOL_LEVEL_LABEL[String(v ?? "prebuilt")] ?? String(v);
      else text = formatValue(v, s.key);
      return { key: s.key, label: s.label, text, list: s.key === "steps" && Array.isArray(v) ? (v as string[]) : null };
    }),
    ...Object.keys(item.fields).filter(isParam).map((k) => ({ key: k, label: fieldLabel(item.kind, k), text: formatValue(item.fields[k], paramName(k)), list: null })),
  ];
  const filled = rows.filter((r) => r.text);
  const shown = all ? rows : filled.slice(0, 5);
  return (
    <div className="space-y-3">
      {item.description && <p className="text-sm leading-relaxed text-muted-foreground">{item.description}</p>}
      <dl className="space-y-2.5 text-sm">
        {shown.map((r) => (
          <div key={r.key} className="grid grid-cols-[minmax(96px,30%)_1fr] gap-3">
            <dt className="text-xs leading-5 text-muted-foreground">{r.label}</dt>
            <dd className="min-w-0 break-words">
              {r.list ? <ol className="list-decimal space-y-1 pl-4">{r.list.map((x, i) => <li key={i}>{x.replace(/\s*\[tool:[^\]]+\]$/, "")}</li>)}</ol> : r.text || <span className="text-muted-foreground">—</span>}
            </dd>
          </div>
        ))}
      </dl>
      {rows.length > shown.length || all ? (
        <button type="button" className="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline" onClick={() => setAll(!all)}>
          {all ? "Show less" : `Show all ${rows.length} settings`}
        </button>
      ) : null}
      {item.kind === "tool" && item.fields.level === "custom" && item.fields.code ? (
        <details className="text-xs">
          <summary className="cursor-pointer select-none text-muted-foreground hover:text-foreground">Advanced: code</summary>
          <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-muted p-3 font-mono text-[11px] leading-relaxed">{String(item.fields.code)}</pre>
        </details>
      ) : null}
    </div>
  );
}
