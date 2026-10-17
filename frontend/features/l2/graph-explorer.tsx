"use client";

import { Box, List, Lock, Network, Search } from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { Suspense, lazy, useMemo, useState } from "react";
import type { GraphNode, NodeType } from "@/contracts";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { KeyValue, LoadingState, Mono, QueryView, StatusChip } from "@/components/brain/primitives";
import { useAgents, useGraph, useHumans } from "@/lib/api/hooks";
import { agentPrincipal, checkEdge, checkNode, humanPrincipal, type Principal } from "@/lib/governance/access";
import { TYPE_COLOR } from "./graph-colors";
import { GraphTabs } from "./graph-tabs";

// React.lazy, not next/dynamic: the chunk loads only when this view renders, never on route prefetch.
const GraphCanvas = lazy(() => import("./graph-canvas"));
const GraphCanvas3D = lazy(() => import("./graph-canvas-3d"));

type Mode = "3d" | "2d" | "list";

const TYPES: NodeType[] = ["agent", "skill", "tool", "policy", "security", "fact", "document", "template", "sensor"];
const HREF: Partial<Record<NodeType, (n: GraphNode) => string>> = {
  agent: (n) => `/l3/agents/${n.refId}`,
  skill: (n) => `/l2/skills/${n.refId}`,
  policy: (n) => `/l2/policies/${n.refId.split("@")[0]}`,
  fact: (n) => `/l2/vault?fact=${n.refId}`,
  document: (n) => `/l2/library?doc=${n.refId}`,
  template: () => "/l2/templates",
  sensor: () => "/l2/sensors",
  security: () => "/l2/security",
};

export function GraphExplorer() {
  const graph = useGraph();
  const agents = useAgents();
  const humans = useHumans();
  const { resolvedTheme } = useTheme();
  const [visible, setVisible] = useState<Set<NodeType>>(new Set(TYPES));
  const [viewAs, setViewAs] = useState<string>("none");
  const [selected, setSelected] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("3d");
  const [query, setQuery] = useState("");

  const principal: Principal | null = useMemo(() => {
    if (viewAs === "none") return null;
    const a = agents.data?.find((x) => x.id === viewAs);
    if (a) return agentPrincipal(a);
    const h = humans.data?.find((x) => x.id === viewAs);
    return h ? humanPrincipal(h) : null;
  }, [viewAs, agents.data, humans.data]);

  const { locked, lockedEdges, lockedEdgeList } = useMemo(() => {
    const locked = new Map<string, string>();
    const lockedEdges = new Set<string>();
    const lockedEdgeList: { id: string; from: string; to: string; reason: string }[] = [];
    if (!principal || !graph.data) return { locked, lockedEdges, lockedEdgeList };
    const nodes = new Map(graph.data.nodes.map((n) => [n.id, n]));
    for (const n of graph.data.nodes) {
      const r = checkNode(principal, n);
      if (!r.allowed) locked.set(n.id, r.reason);
    }
    const self = principal.kind === "agent" ? `n:${principal.id}` : null;
    for (const e of graph.data.edges) {
      const target = nodes.get(e.target);
      if (!target) continue;
      const r = checkEdge(principal, e, target);
      if (!r.allowed && (e.source === self || e.requiresCapability)) {
        lockedEdges.add(e.id);
        if (e.source === self) lockedEdgeList.push({ id: e.id, from: nodes.get(e.source)?.label ?? e.source, to: target.label, reason: r.reason });
      }
    }
    return { locked, lockedEdges, lockedEdgeList };
  }, [principal, graph.data]);

  const sel = graph.data?.nodes.find((n) => n.id === selected) ?? null;
  const selCheck = sel && principal ? checkNode(principal, sel) : null;
  const neighbours = useMemo(() => {
    if (!sel || !graph.data) return [];
    const ids = new Set(graph.data.edges.filter((e) => e.source === sel.id || e.target === sel.id).map((e) => (e.source === sel.id ? e.target : e.source)));
    return graph.data.nodes.filter((n) => ids.has(n.id)).slice(0, 30);
  }, [sel, graph.data]);

  // Search by name; picking a result selects the node, which lights up what it connects to.
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !graph.data) return [];
    return graph.data.nodes.filter((n) => visible.has(n.type) && n.label.toLowerCase().includes(q)).slice(0, 8);
  }, [query, graph.data, visible]);
  const pick = (id: string) => {
    setSelected(id);
    setQuery("");
  };

  const panel = "rounded-xl border bg-card/90 shadow-md backdrop-blur";
  return (
    <div className="relative -mx-3 -my-4 h-[calc(100dvh-3rem)] min-h-[520px] overflow-hidden sm:-mx-6 sm:-my-5">
      <h1 className="sr-only">Knowledge graph</h1>
      <QueryView query={graph}>
        {(g) => (
          <>
            <div className="absolute inset-0">
              {mode === "list" ? (
                <ul className="scrollbar-thin h-full content-start gap-1.5 overflow-auto px-3 pb-4 pt-16 sm:grid-cols-2 lg:grid lg:pl-64 lg:pr-[344px] xl:grid-cols-3" aria-label="Graph nodes">
                  {g.nodes
                    .filter((n) => visible.has(n.type))
                    .slice(0, 600)
                    .map((n) => (
                      <li key={n.id} className="mb-1.5 flex items-center gap-2 rounded-md border bg-card px-2 py-1.5 text-xs lg:mb-0">
                        <span className="size-2 shrink-0 rounded-full" style={{ background: TYPE_COLOR[n.type] }} aria-hidden />
                        <button type="button" className="truncate text-left hover:underline" onClick={() => setSelected(n.id)}>{n.label}</button>
                        <span className="ml-auto shrink-0 text-muted-foreground">{n.type}</span>
                        {locked.has(n.id) && <StatusChip tone="risk"><Lock className="size-3" /> locked</StatusChip>}
                      </li>
                    ))}
                </ul>
              ) : (
                <div className="h-full bg-card">
                  <Suspense fallback={<LoadingState rows={4} label="Loading graph" />}>
                    {mode === "3d" ? (
                      <GraphCanvas3D data={g} visibleTypes={visible} locked={locked} lockedEdges={lockedEdges} selected={selected} onSelect={setSelected} dark={(resolvedTheme === "dark" || resolvedTheme === "black")} />
                    ) : (
                      <GraphCanvas data={g} visibleTypes={visible} locked={locked} lockedEdges={lockedEdges} selected={selected} onSelect={setSelected} dark={(resolvedTheme === "dark" || resolvedTheme === "black")} />
                    )}
                  </Suspense>
                </div>
              )}
            </div>

            <div className="absolute left-3 top-3 z-10 flex flex-wrap items-center gap-2">
              <GraphTabs />
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && matches[0]) pick(matches[0].id);
                    if (e.key === "Escape") setQuery("");
                  }}
                  placeholder="Search a node"
                  aria-label="Search a node"
                  data-testid="graph-search"
                  className="h-8 w-56 rounded-full border bg-card/90 pl-8 pr-3 text-[13px] shadow-sm outline-none backdrop-blur placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
                />
                {query.trim() && (
                  <ul className={`${panel} absolute left-0 top-10 w-72 overflow-hidden p-1`} role="listbox" aria-label="Matching nodes">
                    {matches.length === 0 && <li className="px-3 py-2 text-[13px] text-muted-foreground">No match</li>}
                    {matches.map((n) => (
                      <li key={n.id}>
                        <button type="button" role="option" aria-selected={false} onClick={() => pick(n.id)} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] hover:bg-sidebar-accent">
                          <span className="size-2 shrink-0 rounded-full" style={{ background: TYPE_COLOR[n.type] }} aria-hidden />
                          <span className="truncate">{n.label}</span>
                          <span className="ml-auto shrink-0 text-xs text-muted-foreground">{n.type}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <ToggleGroup type="single" value={mode} onValueChange={(v) => v && setMode(v as Mode)} variant="outline" size="sm" className="rounded-full bg-card/90 shadow-sm backdrop-blur" aria-label="Graph view">
                <ToggleGroupItem value="3d" aria-label="3D graph" className="rounded-l-full px-3"><Box /> 3D</ToggleGroupItem>
                <ToggleGroupItem value="2d" aria-label="2D graph" className="px-3"><Network /> 2D</ToggleGroupItem>
                <ToggleGroupItem value="list" aria-label="List view" className="rounded-r-full px-3"><List /> List</ToggleGroupItem>
              </ToggleGroup>
              <Select value={viewAs} onValueChange={setViewAs}>
                <SelectTrigger size="sm" className="w-[220px] bg-card/90 text-xs shadow-sm backdrop-blur" aria-label="View as">
                  <SelectValue placeholder="View as…" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">View as: everything</SelectItem>
                  <SelectGroup>
                    <SelectLabel>Agents</SelectLabel>
                    {(agents.data ?? []).slice(0, 200).map((a) => (
                      <SelectItem key={a.id} value={a.id}>View as {a.name}</SelectItem>
                    ))}
                  </SelectGroup>
                  <SelectGroup>
                    <SelectLabel>People</SelectLabel>
                    {(humans.data ?? []).map((h) => (
                      <SelectItem key={h.id} value={h.id}>View as {h.name}</SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <span className="rounded-full bg-card/90 px-2.5 py-1 text-[11px] text-muted-foreground shadow-sm backdrop-blur tabular">{g.nodes.length.toLocaleString()} nodes · {g.edges.length.toLocaleString()} edges</span>
            </div>

            <div className={`${panel} absolute bottom-3 left-3 z-10 hidden max-h-[calc(100%-4.5rem)] w-48 flex-col p-3 lg:flex`} role="group" aria-label="Layers">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-xs font-semibold">Layers</h2>
                <button type="button" className="text-[11px] text-primary hover:underline" onClick={() => setVisible(visible.size === TYPES.length ? new Set() : new Set(TYPES))}>
                  {visible.size === TYPES.length ? "Hide all" : "Show all"}
                </button>
              </div>
              <div className="space-y-0.5 overflow-auto">
                {TYPES.map((t) => (
                  <div key={t} className="flex min-h-6 items-center gap-2">
                    <Checkbox
                      id={`layer-${t}`}
                      checked={visible.has(t)}
                      onCheckedChange={(v) => {
                        const next = new Set(visible);
                        if (v) next.add(t);
                        else next.delete(t);
                        setVisible(next);
                      }}
                    />
                    <Label htmlFor={`layer-${t}`} className="flex flex-1 items-center gap-1.5 text-xs capitalize">
                      <span className="size-2.5 rounded-full" style={{ background: TYPE_COLOR[t] }} aria-hidden />
                      {t}
                    </Label>
                  </div>
                ))}
              </div>
            </div>

            <div className={`${panel} absolute right-3 top-14 z-10 hidden max-h-[calc(100%-4.5rem)] w-80 flex-col overflow-hidden lg:flex`}>
              <div className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto p-3">
                <div>
                  <h2 className="text-sm font-semibold">{sel ? sel.label : "Select a node"}</h2>
                  <p className="mt-0.5 text-xs text-muted-foreground">{sel ? `${sel.type} · ${sel.sensitivity}` : "Click a node to inspect it. Pick a principal in “view as” to see locks."}</p>
                </div>
                {sel && (
                  <div className="space-y-3">
                    {selCheck && !selCheck.allowed && (
                      <p className="flex items-start gap-1.5 rounded-md bg-risk/10 p-2 text-xs text-risk">
                        <Lock className="mt-0.5 size-3.5 shrink-0" /> Locked: {selCheck.reason}
                      </p>
                    )}
                    <KeyValue items={[["Id", <Mono key="i">{sel.refId}</Mono>], ["Requires", sel.requires.capability ? <Mono key="c">{sel.requires.capability}</Mono> : sel.requires.roles.length ? sel.requires.roles.join(", ") : "nothing extra"]]} />
                    {HREF[sel.type] && (
                      <Link href={HREF[sel.type]!(sel)} className="text-xs text-primary hover:underline">
                        Open {sel.type}
                      </Link>
                    )}
                    <div>
                      <div className="mb-1 text-xs font-medium">Connected ({neighbours.length})</div>
                      <ul className="max-h-48 space-y-1 overflow-auto text-xs">
                        {neighbours.map((n) => (
                          <li key={n.id}>
                            <button type="button" className="flex items-center gap-1.5 hover:underline" onClick={() => setSelected(n.id)}>
                              <span className="size-2 rounded-full" style={{ background: TYPE_COLOR[n.type] }} />
                              {locked.has(n.id) && <Lock className="size-3 text-risk" />}
                              {n.label}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
                {principal && (
                  <div>
                    <div className="mb-1 text-xs font-semibold">What {principal.name} cannot reach <span className="font-normal text-muted-foreground">({locked.size} locked nodes)</span></div>
                    <ul className="max-h-64 space-y-1.5 overflow-auto text-xs" data-testid="locked-edges">
                      {lockedEdgeList.length === 0 && <li className="text-muted-foreground">No locked edges from this principal.</li>}
                      {lockedEdgeList.map((e) => (
                        <li key={e.id} className="rounded-md border border-risk/30 p-2">
                          <div className="flex items-center gap-1.5 font-medium">
                            <Lock className="size-3 text-risk" /> {e.from} → {e.to}
                          </div>
                          <div className="mt-0.5 text-muted-foreground">{e.reason}</div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </QueryView>
    </div>
  );
}
