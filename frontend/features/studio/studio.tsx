"use client";

import { ChevronsUpDown, Download, ExternalLink, LayoutList, MessagesSquare, Network, Plus, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, lazy, useCallback, useMemo, useState } from "react";
import type { WorkflowDetail, WorkflowSummary } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { PersonChip, useLookup } from "@/components/brain/names";
import { CritBadge, EmptyState, ErrorState, LoadingState, StatusChip } from "@/components/brain/primitives";
import { useNow, useStudioWorkflow, useStudioWorkflows } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { downloadDrawio, drawioUrl, toDrawioXml } from "@/lib/studio/drawio";
import { KIND_COLOR, NO_HIGHLIGHT, type Highlight } from "@/lib/studio/graph";
import { KIND_PLURAL, MEMBER_ORDER } from "@/lib/studio/spec";
import { cn } from "@/lib/utils";
import { StudioChat } from "./chat";
import { DetailsPanel } from "./details-panel";
import { PartsView } from "./parts";
import { useStudio, type Focus } from "./state";

// React.lazy, not next/dynamic: the canvas chunk loads only when the diagram view renders.
const WorkflowDiagram = lazy(() => import("./workflow-diagram"));

type View = "chat" | "diagram" | "parts";

export function WorkflowStudio() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const workflows = useStudioWorkflows();
  const list = workflows.data ?? [];
  const wfId = params.get("wf") && list.some((w) => w.id === params.get("wf")) ? params.get("wf")! : list[0]?.id ?? "";
  const view = (["chat", "diagram", "parts"].includes(params.get("view") ?? "") ? params.get("view") : "chat") as View;
  const detail = useStudioWorkflow(wfId);
  const now = useNow();
  const stored = useStudio((s) => s.focus[wfId]);
  // A link like /studio?wf=…&focus=… opens on that part until the person picks something else.
  const linked = params.get("focus") ? detail.data?.items.find((i) => i.id === params.get("focus")) : undefined;
  const focus = stored !== undefined ? stored : linked ? { kind: linked.kind, id: linked.id } : null;
  const setFocusFor = useStudio((s) => s.setFocus);
  const setDraft = useStudio((s) => s.setDraft);
  // A highlight belongs to the workflow it was made for, so switching workflows clears it.
  const [lit, setLit] = useState<{ wf: string; h: Highlight }>({ wf: "", h: NO_HIGHLIGHT });
  const highlight = lit.wf === wfId ? lit.h : NO_HIGHLIGHT;
  const setHighlight = (h: Highlight) => setLit({ wf: wfId, h });

  const go = useCallback(
    (next: { wf?: string; view?: View }) => {
      const q = new URLSearchParams(params.toString());
      if (next.wf) q.set("wf", next.wf);
      if (next.view) q.set("view", next.view);
      router.replace(`${pathname}?${q.toString()}`, { scroll: false });
    },
    [params, pathname, router],
  );
  const setFocus = useCallback((f: Focus) => setFocusFor(wfId, f), [setFocusFor, wfId]);

  if (workflows.isLoading) return <LoadingState rows={8} label="Loading workflows" />;
  if (workflows.error) return <ErrorState error={workflows.error} onRetry={() => workflows.refetch()} />;
  if (!list.length) return <EmptyState title="No workflows yet" description="Workflows appear here once the brain has skills and agents." />;

  const showDiagram = (h: Highlight) => {
    setHighlight(h);
    go({ view: "diagram" });
  };

  return (
    <div className="flex flex-col gap-3 lg:h-[calc(100dvh-7rem)]">
      <StudioHeader list={list} current={list.find((w) => w.id === wfId)!} view={view} detail={detail.data} highlight={highlight} onPick={(id) => go({ wf: id })} onView={(v) => go({ view: v })} onNew={() => { go({ view: "chat" }); setDraft('Create a new workflow called "…" that …'); }} />
      {detail.isLoading || !detail.data ? (
        detail.error ? <ErrorState error={detail.error} onRetry={() => detail.refetch()} /> : <LoadingState rows={8} />
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] gap-3 lg:grid-cols-[minmax(0,3fr)_minmax(280px,1fr)]">
          <div className="min-h-[560px] lg:min-h-0">
            {view === "chat" && <StudioChat workflowId={wfId} detail={detail.data} focus={focus} now={now} onFocus={setFocus} onSwitch={(id) => go({ wf: id })} onShowDiagram={showDiagram} />}
            {view === "diagram" && <DiagramView detail={detail.data} highlight={highlight} focusId={focus?.id ?? null} onClear={() => setHighlight(NO_HIGHLIGHT)} onSelect={(id) => { const it = detail.data!.items.find((i) => i.id === id); if (it) setFocus({ kind: it.kind, id }); }} />}
            {view === "parts" && <PartsView detail={detail.data} focus={focus} onFocus={setFocus} onShowDiagram={showDiagram} />}
          </div>
          <div className="min-h-[420px] lg:min-h-0">
            <DetailsPanel
              detail={detail.data}
              summaries={list}
              focus={focus}
              now={now}
              onFocus={setFocus}
              onAsk={(p) => { setDraft(p); go({ view: "chat" }); }}
              onSwitch={(id) => go({ wf: id })}
              onShowOnDiagram={(id) => showDiagram({ target: id, affected: new Set(), broken: new Set() })}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function StudioHeader({ list, current, view, detail, highlight, onPick, onView, onNew }: { list: WorkflowSummary[]; current: WorkflowSummary; view: View; detail: WorkflowDetail | undefined; highlight: Highlight; onPick: (id: string) => void; onView: (v: View) => void; onNew: () => void }) {
  const [open, setOpen] = useState(false);
  const { user } = useCurrentUser();
  const lookup = useLookup();
  return (
    <div className="flex flex-col gap-2 rounded-xl border bg-card px-3 py-2.5 shadow-xs xl:flex-row xl:items-center">
      <h1 className="sr-only">Workflow Studio: {current.name}</h1>
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" className="h-auto min-w-0 max-w-full justify-between gap-2 py-1.5 text-left" aria-label="Pick a workflow">
              <span className="min-w-0">
                <span className="block text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Workflow Studio</span>
                <span className="block truncate text-sm font-semibold">{current.name}</span>
              </span>
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
        <div className="hidden min-w-0 flex-1 md:block">
          <p className="line-clamp-1 text-xs text-muted-foreground">{current.description}</p>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className="text-muted-foreground">DRI</span> <PersonChip id={current.dri} />
            <CritBadge level={current.criticality} />
            {current.health.breaks > 0 ? <StatusChip tone="risk">{current.health.breaks} break{current.health.breaks === 1 ? "" : "s"}</StatusChip> : <StatusChip tone="ok">healthy</StatusChip>}
            {current.health.warnings > 0 && <StatusChip tone="warn">{current.health.warnings} warning{current.health.warnings === 1 ? "" : "s"}</StatusChip>}
            {current.pending > 0 && <StatusChip tone="warn">{current.pending} awaiting approval</StatusChip>}
            {user?.tier === "L3" && <StatusChip tone="neutral">view only</StatusChip>}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {view === "diagram" && detail && <DrawioButtons detail={detail} highlight={highlight} />}
        <ToggleGroup type="single" value={view} onValueChange={(v) => v && onView(v as View)} variant="outline" size="sm" aria-label="View">
          <ToggleGroupItem value="chat" aria-label="Chat"><MessagesSquare /> <span className="max-sm:hidden">Chat</span></ToggleGroupItem>
          <ToggleGroupItem value="diagram" aria-label="Diagram"><Network /> <span className="max-sm:hidden">Diagram</span></ToggleGroupItem>
          <ToggleGroupItem value="parts" aria-label="Parts"><LayoutList /> <span className="max-sm:hidden">Parts</span></ToggleGroupItem>
        </ToggleGroup>
        {user?.tier !== "L3" && (
          <Button size="sm" variant="outline" onClick={onNew}>
            <Plus /> New workflow
          </Button>
        )}
      </div>
    </div>
  );
}

function DrawioButtons({ detail, highlight }: { detail: WorkflowDetail; highlight: Highlight }) {
  const xml = useMemo(() => toDrawioXml(detail, highlight), [detail, highlight]);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <Button
        size="sm"
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
      <Button size="sm" variant="ghost" onClick={() => downloadDrawio(xml, detail.workflow.name)} aria-label="Download as .drawio">
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
        <span className="ml-auto">Left to right: what wakes it, who works, what they do, what limits and powers them, what they report.</span>
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
