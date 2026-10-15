"use client";

import { ChevronsUpDown, Download, ExternalLink, Plus, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, lazy, useCallback, useMemo, useState } from "react";
import type { WorkflowDetail, WorkflowSummary } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useLookup } from "@/components/brain/names";
import { CritBadge, EmptyState, ErrorState, LoadingState, StatusChip } from "@/components/brain/primitives";
import { useNow, useStudioWorkflow, useStudioWorkflows } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { downloadDrawio, drawioUrl, toDrawioXml } from "@/lib/studio/drawio";
import { KIND_COLOR, NO_HIGHLIGHT, type Highlight } from "@/lib/studio/graph";
import { KIND_PLURAL, MEMBER_ORDER } from "@/lib/studio/spec";
import { cn } from "@/lib/utils";
import { StudioChat } from "./chat";
import { PartsPane, type PaneMode } from "./parts-pane";
import { useStudio, type ChatMessage, type Focus } from "./state";
import { stepOf, type StepKey } from "./steps";

// React.lazy, not next/dynamic: the canvas chunk loads only when the diagram view renders.
const WorkflowDiagram = lazy(() => import("./workflow-diagram"));

const EMPTY: ChatMessage[] = [];

export function WorkflowStudio() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const workflows = useStudioWorkflows();
  const list = workflows.data ?? [];
  const wfId = params.get("wf") && list.some((w) => w.id === params.get("wf")) ? params.get("wf")! : list[0]?.id ?? "";
  // Chat is always on the left. The view param only picks what the right pane shows; old "chat" and "parts" links land on parts.
  const mode: PaneMode = params.get("view") === "diagram" ? "diagram" : "parts";
  const detail = useStudioWorkflow(wfId);
  const now = useNow();
  const thread = useStudio((s) => s.threads[wfId] ?? EMPTY);
  const stored = useStudio((s) => s.focus[wfId]);
  const storedStep = useStudio((s) => s.step[wfId]);
  // A link like /studio?wf=…&focus=… opens on that part until the person picks something else.
  const linked = params.get("focus") ? detail.data?.items.find((i) => i.id === params.get("focus")) : undefined;
  const focus = stored !== undefined ? stored : linked ? { kind: linked.kind, id: linked.id } : null;
  const setFocusFor = useStudio((s) => s.setFocus);
  const setStepFor = useStudio((s) => s.setStep);
  const setDraft = useStudio((s) => s.setDraft);
  // A highlight belongs to the workflow it was made for, so switching workflows clears it.
  const [lit, setLit] = useState<{ wf: string; h: Highlight }>({ wf: "", h: NO_HIGHLIGHT });
  const highlight = lit.wf === wfId ? lit.h : NO_HIGHLIGHT;
  const setHighlight = (h: Highlight) => setLit({ wf: wfId, h });

  // Until the person picks a step, open where the focused part lives, else where something needs fixing, else at the start.
  // Until the person picks a step, open where the focused part lives, else on the story.
  const fromFocus = focus && focus.kind !== "workflow" ? stepOf(focus.kind) : null;
  const step: StepKey = storedStep ?? fromFocus ?? "story";

  const go = useCallback(
    (next: { wf?: string; view?: PaneMode }) => {
      const q = new URLSearchParams(params.toString());
      if (next.wf) q.set("wf", next.wf);
      if (next.view) q.set("view", next.view);
      router.replace(`${pathname}?${q.toString()}`, { scroll: false });
    },
    [params, pathname, router],
  );
  // Focusing a part also turns the pane to its step, so whatever the chat is talking about is in view.
  const setFocus = useCallback(
    (f: Focus) => {
      setFocusFor(wfId, f);
      const s = f && f.kind !== "workflow" ? stepOf(f.kind) : null;
      if (s) setStepFor(wfId, s);
    },
    [setFocusFor, setStepFor, wfId],
  );

  if (workflows.isLoading) return <LoadingState rows={8} label="Loading workflows" />;
  if (workflows.error) return <ErrorState error={workflows.error} onRetry={() => workflows.refetch()} />;
  if (!list.length) return <EmptyState title="No workflows yet" description="Workflows appear here once the brain has skills and agents." />;

  const showDiagram = (h: Highlight) => {
    setHighlight(h);
    go({ view: "diagram" });
  };

  const controls = <StudioControls list={list} current={list.find((w) => w.id === wfId)!} onPick={(id) => go({ wf: id })} onNew={() => setDraft('Create a new workflow called "…" that …')} />;

  // Full bleed: chat on the left, the workflow's parts on the right, so every answer is visible where it lands.
  return (
    <div className="-mx-3 -my-4 flex flex-col sm:-mx-6 sm:-my-5 lg:h-[calc(100dvh-3rem)]">
      <h1 className="sr-only">Workflow Studio: {list.find((w) => w.id === wfId)?.name}</h1>
      {detail.isLoading || !detail.data ? (
        <div className="p-4">{detail.error ? <ErrorState error={detail.error} onRetry={() => detail.refetch()} /> : <LoadingState rows={8} />}</div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] lg:grid-cols-[minmax(360px,2fr)_minmax(0,3fr)]">
          <div className="min-h-[560px] lg:min-h-0 lg:border-r">
            <StudioChat workflowId={wfId} detail={detail.data} focus={focus} now={now} onFocus={setFocus} onSwitch={(id) => go({ wf: id })} onShowDiagram={showDiagram} toolbar={controls} />
          </div>
          <div className="min-h-[560px] lg:min-h-0">
            <PartsPane
              detail={detail.data}
              summaries={list}
              thread={thread}
              focus={focus}
              step={step}
              mode={mode}
              now={now}
              onStep={(s) => setStepFor(wfId, s)}
              onMode={(m) => go({ view: m })}
              onFocus={setFocus}
              onAsk={(p) => setDraft(p)}
              onSwitch={(id) => go({ wf: id })}
              onShowDiagram={showDiagram}
              diagram={<DiagramView detail={detail.data} highlight={highlight} focusId={focus?.id ?? null} onClear={() => setHighlight(NO_HIGHLIGHT)} onSelect={(id) => { const it = detail.data!.items.find((i) => i.id === id); if (it) setFocus({ kind: it.kind, id }); }} />}
            />
          </div>
        </div>
      )}
    </div>
  );
}

/** Compact controls in the chat header: workflow picker and new workflow. */
function StudioControls({ list, current, onPick, onNew }: { list: WorkflowSummary[]; current: WorkflowSummary; onPick: (id: string) => void; onNew: () => void }) {
  const [open, setOpen] = useState(false);
  const { user } = useCurrentUser();
  const lookup = useLookup();
  return (
    <div className="flex items-center gap-1.5">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="max-w-[220px] justify-between gap-2 text-left" aria-label="Pick a workflow">
            <span className="truncate text-[13px] font-semibold">{current.name}</span>
            <ChevronsUpDown className="size-4 shrink-0 opacity-60" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[min(420px,90vw)] p-0" align="start">
          <Command>
            <CommandInput placeholder="Find a workflow, topic or cluster…" />
            <CommandList className="max-h-[60vh]">
              <CommandEmpty>No workflow matches.</CommandEmpty>
              <CommandGroup heading={`${list.length} workflows`}>
                {list.map((w) => (
                  <CommandItem key={w.id} value={`${w.name} ${w.topics.join(" ")} ${lookup.cluster(w.clusterId)}`} onSelect={() => { onPick(w.id); setOpen(false); }} className="flex items-start gap-2 py-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-sm font-medium">{w.name}</span>
                        {w.health.breaks > 0 && <StatusChip tone="risk" className="h-4 px-1.5 text-[10px]">{w.health.breaks} break{w.health.breaks === 1 ? "" : "s"}</StatusChip>}
                        {w.pending > 0 && <StatusChip tone="warn" className="h-4 px-1.5 text-[10px]">{w.pending} pending</StatusChip>}
                      </div>
                      <div className="truncate text-[11px] text-muted-foreground">{MEMBER_ORDER.filter((k) => w.counts[k]).map((k) => `${w.counts[k]} ${KIND_PLURAL[k].toLowerCase()}`).join(" · ")}</div>
                    </div>
                    <CritBadge level={w.criticality} />
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {user?.tier !== "L3" && (
        <Button size="icon-sm" variant="ghost" onClick={onNew} aria-label="New workflow">
          <Plus />
        </Button>
      )}
    </div>
  );
}

function DrawioButtons({ detail, highlight }: { detail: WorkflowDetail; highlight: Highlight }) {
  const xml = useMemo(() => toDrawioXml(detail, highlight), [detail, highlight]);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <Button
        size="xs"
        variant="outline"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            window.open(await drawioUrl(xml), "_blank", "noopener,noreferrer");
          } finally {
            setBusy(false);
          }
        }}
      >
        <ExternalLink /> Open in draw.io
      </Button>
      <Button size="xs" variant="ghost" onClick={() => downloadDrawio(xml, detail.workflow.name)} aria-label="Download as .drawio">
        <Download /> <span className="max-sm:hidden">.drawio</span>
      </Button>
    </>
  );
}

function DiagramView({ detail, highlight, focusId, onSelect, onClear }: { detail: WorkflowDetail; highlight: Highlight; focusId: string | null; onSelect: (id: string) => void; onClear: () => void }) {
  const lit = !!highlight.target || highlight.affected.size > 0;
  return (
    <div className="flex h-full min-h-[560px] flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        {MEMBER_ORDER.map((k) => (
          <span key={k} className="inline-flex items-center gap-1">
            <span className="size-2.5 rounded-sm" style={{ background: KIND_COLOR[k] }} aria-hidden />
            {KIND_PLURAL[k]}
          </span>
        ))}
        <span className="ml-auto flex items-center gap-1"><DrawioButtons detail={detail} highlight={highlight} /></span>
      </div>
      {lit && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-surface px-2.5 py-1.5 text-xs">
          <span className={cn("inline-flex items-center gap-1")}><span className="size-2.5 rounded-full ring-2 ring-primary" />target</span>
          <span className="inline-flex items-center gap-1"><span className="size-2.5 rounded-full ring-2 ring-warn" />affected</span>
          <span className="inline-flex items-center gap-1"><span className="size-2.5 rounded-full ring-2 ring-risk" />would break</span>
          <span className="text-muted-foreground">Everything else is dimmed.</span>
          <Button size="xs" variant="ghost" className="ml-auto" onClick={onClear}><X /> Clear highlight</Button>
        </div>
      )}
      <div className="min-h-0 flex-1">
        <Suspense fallback={<div className="h-full animate-pulse rounded-xl border bg-surface" />}>
          <WorkflowDiagram detail={detail} highlight={highlight} focusId={focusId} onSelect={onSelect} />
        </Suspense>
      </div>
    </div>
  );
}
