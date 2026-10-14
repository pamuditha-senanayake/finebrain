"use client";

import { Background, Controls, Handle, MarkerType, Position, ReactFlow, useReactFlow, useStore, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo } from "react";
import type { StudioItem, WorkflowDetail } from "@/contracts";
import { KIND_COLOR, NO_HIGHLIGHT, layout, type Highlight } from "@/lib/studio/graph";
import { KIND_LABEL } from "@/lib/studio/spec";
import { cn } from "@/lib/utils";

type Data = { item: StudioItem; sharedBy: number; state: "target" | "broken" | "affected" | "dim" | "plain"; focused: boolean };

function ItemNode({ data }: NodeProps<Node<Data>>) {
  const { item, sharedBy, state, focused } = data;
  const color = KIND_COLOR[item.kind];
  return (
    <div
      className={cn(
        "w-[196px] rounded-xl border bg-card px-2.5 py-1.5 text-left shadow-xs transition-opacity",
        state === "dim" && "opacity-35",
        state === "target" && "ring-2 ring-primary",
        state === "broken" && "ring-2 ring-risk",
        state === "affected" && "ring-2 ring-warn",
        focused && state === "plain" && "ring-2 ring-primary/50",
        item.status !== "active" && "border-dashed",
      )}
      style={{ borderLeft: `4px solid ${color}` }}
    >
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-muted-foreground" />
      <div className="flex items-center justify-between gap-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <span className="size-1.5 rounded-full" style={{ background: color }} aria-hidden />
          {KIND_LABEL[item.kind]}
        </span>
        {sharedBy > 1 && <span className="rounded bg-muted px-1 text-muted-foreground normal-case">shared ×{sharedBy}</span>}
        {item.status !== "active" && <span className="text-muted-foreground normal-case">{item.status}</span>}
      </div>
      <div className="truncate text-xs font-medium text-foreground" title={item.name}>{item.name}</div>
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-muted-foreground" />
    </div>
  );
}

const nodeTypes = { item: ItemNode };

/** Refits when the pane is resized or the set of nodes changes, so a panel resize never leaves the map tiny. */
function AutoFit({ signature }: { signature: string }) {
  const { fitView } = useReactFlow();
  const width = useStore((s) => s.width);
  const height = useStore((s) => s.height);
  useEffect(() => {
    if (width && height) void fitView({ padding: 0.12, duration: 0 });
  }, [width, height, signature, fitView]);
  return null;
}

/** The whole workflow on one canvas. During a review, the target and everything it touches stay lit and the rest dims. */
export default function WorkflowDiagram({ detail, highlight = NO_HIGHLIGHT, focusId, onSelect, compact = false }: { detail: WorkflowDetail; highlight?: Highlight; focusId?: string | null; onSelect?: (id: string) => void; compact?: boolean }) {
  const { nodes, edges } = useMemo(() => {
    const g = layout(detail);
    const reviewing = !!highlight.target || highlight.affected.size > 0 || highlight.broken.size > 0;
    const lit = new Set([highlight.target, ...highlight.affected, ...highlight.broken].filter(Boolean) as string[]);
    const nodes: Node<Data>[] = g.nodes.map((n) => ({
      id: n.id, type: "item", position: { x: n.x, y: n.y },
      data: {
        item: n.item, sharedBy: n.sharedBy, focused: n.id === focusId,
        state: highlight.broken.has(n.id) ? "broken" : highlight.target === n.id ? "target" : highlight.affected.has(n.id) ? "affected" : reviewing ? "dim" : "plain",
      },
    }));
    const edges: Edge[] = g.edges.map((e) => {
      const hot = reviewing && lit.has(e.source) && lit.has(e.target);
      return {
        id: e.id, source: e.source, target: e.target, label: compact ? undefined : e.rel,
        labelStyle: { fontSize: 9, fill: "var(--muted-foreground)" }, labelBgStyle: { fill: "var(--card)" },
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
        animated: hot,
        style: { stroke: hot ? "var(--primary)" : e.faint ? "var(--border)" : "var(--muted-foreground)", strokeWidth: hot ? 2 : 1, strokeDasharray: e.faint ? "4 3" : undefined, opacity: reviewing && !hot ? 0.3 : 1 },
      };
    });
    return { nodes, edges };
  }, [detail, highlight, focusId, compact]);

  return (
    <div className={cn("h-full w-full rounded-xl border bg-surface", compact ? "min-h-[220px]" : "min-h-[420px]")} aria-label={`${detail.workflow.name} workflow diagram`}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        minZoom={0.2}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={!compact}
        nodesConnectable={false}
        elementsSelectable={!!onSelect}
        onNodeClick={(_, n) => onSelect?.(n.id)}
        panOnScroll={!compact}
        zoomOnScroll={!compact}
      >
        <Background gap={20} size={1} />
        <AutoFit signature={nodes.map((n) => n.id).join("|")} />
        {!compact && <Controls showInteractive={false} position="bottom-right" className="overflow-hidden rounded-lg border shadow-xs [&_button]:border-border [&_button]:bg-card [&_button]:fill-foreground [&_button:hover]:bg-accent" />}
      </ReactFlow>
    </div>
  );
}
