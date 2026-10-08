"use client";

import { Background, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { Loop, LoopStage } from "@/contracts";

const STAGE_COLOR: Record<LoopStage["key"], string> = { sensor: "#ec4899", policy: "#f59e0b", tool: "#10b981", gate: "#0ea5e9", learning: "#8b5cf6" };

function StageNode({ data }: NodeProps<Node<{ stage: LoopStage }>>) {
  const s = data.stage;
  return (
    <div className="w-[190px] rounded-xl border bg-card p-2.5 text-left shadow-sm" style={{ borderColor: STAGE_COLOR[s.key] }}>
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-muted-foreground" />
      <div className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: STAGE_COLOR[s.key] }}>{s.key}</div>
      <div className="truncate text-xs font-medium text-foreground">{s.label}</div>
      <div className="mt-1 flex items-baseline justify-between text-[11px] text-muted-foreground">
        <span>{s.metric.label}</span>
        <span className="font-semibold text-foreground tabular">{s.metric.value}</span>
      </div>
      {s.pending > 0 && <div className="mt-1 rounded bg-warn/15 px-1 text-[10px] text-foreground">{s.pending} pending</div>}
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-muted-foreground" />
    </div>
  );
}

const nodeTypes = { stage: StageNode };

/** Sensor → policy → tool → quality gate → learning → back to the sensor. */
export default function LoopCanvas({ loop }: { loop: Loop }) {
  const { nodes, edges } = useMemo(() => {
    const positions = [
      { x: 0, y: 90 },
      { x: 240, y: 0 },
      { x: 480, y: 90 },
      { x: 360, y: 230 },
      { x: 120, y: 230 },
    ];
    const nodes: Node[] = loop.stages.map((s, i) => ({ id: s.key, type: "stage", position: positions[i], data: { stage: s } }));
    const edges: Edge[] = loop.stages.map((s, i) => {
      const next = loop.stages[(i + 1) % loop.stages.length];
      return { id: `${s.key}-${next.key}`, source: s.key, target: next.key, animated: true, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: STAGE_COLOR[s.key] } };
    });
    return { nodes, edges };
  }, [loop]);
  return (
    <div className="h-[340px] rounded-xl border bg-surface" aria-label={`${loop.name} loop canvas`}>
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView proOptions={{ hideAttribution: true }} nodesDraggable={false} nodesConnectable={false}>
        <Background gap={20} size={1} />
      </ReactFlow>
    </div>
  );
}
