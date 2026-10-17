"use client";

import Graph from "graphology";
import { useEffect, useRef } from "react";
import Sigma from "sigma";
import type { Graph as GraphData, NodeType } from "@/contracts";
import { TYPE_COLOR } from "./graph-colors";

type Props = {
  data: GraphData;
  visibleTypes: Set<NodeType>;
  locked: Map<string, string>;
  lockedEdges: Set<string>;
  selected: string | null;
  onSelect: (id: string | null) => void;
  dark: boolean;
};

/** WebGL knowledge graph. Loaded lazily so Sigma stays out of every route's initial bundle. */
export default function GraphCanvas({ data, visibleTypes, locked, lockedEdges, selected, onSelect, dark }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const sigma = useRef<Sigma | null>(null);
  const state = useRef({ visibleTypes, locked, lockedEdges, selected });

  useEffect(() => {
    if (!container.current) return;
    const g = new Graph({ multi: true });
    const degree = new Map<string, number>();
    for (const e of data.edges) {
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    }
    const big = data.nodes.length > 600;
    for (const n of data.nodes) {
      g.addNode(n.id, { x: n.x, y: n.y, size: Math.min(14, (big ? 1.6 : 3) + Math.sqrt(degree.get(n.id) ?? 0) * (big ? 0.6 : 1.4)), color: TYPE_COLOR[n.type], label: n.label, nodeType: n.type });
    }
    for (const e of data.edges) if (g.hasNode(e.source) && g.hasNode(e.target)) g.addEdgeWithKey(e.id, e.source, e.target, { size: big ? 0.4 : 1, color: dark ? "#33405a" : "#cbd5e1" });
    const renderer = new Sigma(g, container.current, {
      renderEdgeLabels: false,
      labelRenderedSizeThreshold: big ? 9 : 6,
      labelColor: { color: dark ? "#cbd5e1" : "#334155" },
      labelSize: 11,
      defaultEdgeType: "line",
      zIndex: true,
      nodeReducer: (node, attrs) => {
        const s = state.current;
        const type = attrs.nodeType as NodeType;
        if (!s.visibleTypes.has(type)) return { ...attrs, hidden: true };
        const out = { ...attrs };
        if (s.locked.has(node)) {
          out.color = dark ? "#3f4657" : "#cbd5e1";
          out.label = `🔒 ${attrs.label}`;
        }
        if (s.selected === node) {
          out.highlighted = true;
          out.size = (attrs.size as number) * 1.6;
          out.zIndex = 2;
        } else if (s.selected && g.hasNode(s.selected)) {
          // Name what the selected node connects to; fade the rest.
          if (g.areNeighbors(node, s.selected)) {
            out.forceLabel = true;
            out.zIndex = 1;
          } else out.color = dark ? "#5b6478" : "#d4d8e0";
        }
        return out;
      },
      edgeReducer: (edge, attrs) => {
        const s = state.current;
        const out = { ...attrs };
        if (s.lockedEdges.has(edge)) {
          out.color = "#ef4444";
          out.size = 1.6;
          out.zIndex = 1;
        }
        if (s.selected) {
          const [a, b] = g.extremities(edge);
          if (a !== s.selected && b !== s.selected) out.color = dark ? "#2f384b" : "#e2e8f0";
        }
        return out;
      },
    });
    renderer.on("clickNode", ({ node }) => onSelect(node));
    renderer.on("clickStage", () => onSelect(null));
    sigma.current = renderer;
    return () => {
      renderer.kill();
      sigma.current = null;
    };
    // The graph is rebuilt only when the data or theme changes. Filters refresh through reducers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, dark]);

  useEffect(() => {
    state.current = { visibleTypes, locked, lockedEdges, selected };
    sigma.current?.refresh();
  }, [visibleTypes, locked, lockedEdges, selected]);

  return <div ref={container} className="h-full w-full" role="img" aria-label={`Knowledge graph with ${data.nodes.length} nodes and ${data.edges.length} edges. Use the list view for a text version.`} data-testid="graph-canvas" />;
}
