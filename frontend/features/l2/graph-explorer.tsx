"use client";

import { Lock, Network } from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { Suspense, lazy, useMemo, useState } from "react";
import type { GraphNode, NodeType } from "@/contracts";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { KeyValue, LoadingState, Mono, PageHeader, QueryView, Section, StatusChip } from "@/components/brain/primitives";
import { useAgents, useGraph, useHumans } from "@/lib/api/hooks";
import { agentPrincipal, checkEdge, checkNode, humanPrincipal, type Principal } from "@/lib/governance/access";
import { TYPE_COLOR } from "./graph-canvas";

// React.lazy, not next/dynamic: the chunk loads only when this view renders, never on route prefetch.
const GraphCanvas = lazy(() => import("./graph-canvas"));

const TYPES: NodeType[] = ["agent", "skill", "tool", "policy", "security", "fact", "document", "template", "sensor"];
const HREF: Partial<Record<NodeType, (n: GraphNode) => string>> = {
  agent: (n) => `/l3/agents/${n.refId}`,
  skill: (n) => `/l2/skills/${n.refId}`,
  policy: (n) => `/l2/policies/${n.refId.split("@")[0]}`,
  fact: (n) => `/l2/vault?fact=${n.refId}`,
  document: () => "/l2/library",
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

  return (
    <div>
      <PageHeader
        title="Knowledge graph"
        description="Skills, policies, security rules, sensors, templates, facts, documents, agents and tools, with access rules on nodes and edges. Use “view as” to see exactly what one agent or person can reach."
        actions={
          <Select value={viewAs} onValueChange={setViewAs}>
            <SelectTrigger size="sm" className="w-[240px] text-xs" aria-label="View as">
              <SelectValue placeholder="View as…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">View as: everything</SelectItem>
              <SelectGroup>
                <SelectLabel>Agents</SelectLabel>
                {(agents.data ?? []).slice(0, 200).map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    View as {a.name}
                  </SelectItem>
                ))}
              </SelectGroup>
              <SelectGroup>
                <SelectLabel>People</SelectLabel>
                {(humans.data ?? []).map((h) => (
                  <SelectItem key={h.id} value={h.id}>
                    View as {h.name}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        }
      />
      <div className="mb-3 flex flex-wrap gap-x-4 gap-y-2" role="group" aria-label="Layers">
        {TYPES.map((t) => (
          <div key={t} className="flex items-center gap-1.5">
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
            <Label htmlFor={`layer-${t}`} className="flex items-center gap-1.5 text-xs capitalize">
              <span className="size-2.5 rounded-full" style={{ background: TYPE_COLOR[t] }} aria-hidden />
              {t}
            </Label>
          </div>
        ))}
      </div>
      <QueryView query={graph}>
        {(g) => (
          <Tabs defaultValue="graph">
            <TabsList>
              <TabsTrigger value="graph"><Network /> Graph</TabsTrigger>
              <TabsTrigger value="list">List view</TabsTrigger>
            </TabsList>
            <TabsContent value="graph">
              <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
                <div className="h-[calc(100dvh-300px)] min-h-[420px] overflow-hidden rounded-xl border bg-card">
                  <Suspense fallback={<LoadingState rows={4} label="Loading graph" />}><GraphCanvas data={g} visibleTypes={visible} locked={locked} lockedEdges={lockedEdges} selected={selected} onSelect={setSelected} dark={resolvedTheme === "dark"} /></Suspense>
                </div>
                <div className="space-y-3">
                  <Section title={sel ? sel.label : "Select a node"} description={sel ? `${sel.type} · ${sel.sensitivity}` : `${g.nodes.length.toLocaleString()} nodes, ${g.edges.length.toLocaleString()} edges`}>
                    {sel ? (
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
                    ) : (
                      <p className="text-xs text-muted-foreground">Click a node to inspect it. Pick a principal in “view as” to see locks.</p>
                    )}
                  </Section>
                  {principal && (
                    <Section title={`What ${principal.name} cannot reach`} description={`${locked.size} locked nodes`}>
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
                    </Section>
                  )}
                </div>
              </div>
            </TabsContent>
            <TabsContent value="list">
              <ul className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3" aria-label="Graph nodes">
                {g.nodes
                  .filter((n) => visible.has(n.type))
                  .slice(0, 600)
                  .map((n) => (
                    <li key={n.id} className="flex items-center gap-2 rounded-md border bg-card px-2 py-1.5 text-xs">
                      <span className="size-2 shrink-0 rounded-full" style={{ background: TYPE_COLOR[n.type] }} aria-hidden />
                      <span className="truncate">{n.label}</span>
                      <span className="ml-auto shrink-0 text-muted-foreground">{n.type}</span>
                      {locked.has(n.id) && <StatusChip tone="risk"><Lock className="size-3" /> locked</StatusChip>}
                    </li>
                  ))}
              </ul>
            </TabsContent>
          </Tabs>
        )}
      </QueryView>
    </div>
  );
}
