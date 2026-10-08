"use client";

import { Background, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { Branch, Commit } from "@/contracts";

/** Branch graph: main as the trunk, sandbox branches forking off it. Lazy loaded. */
export default function BranchGraph({ branches, commits }: { branches: Branch[]; commits: Commit[] }) {
  const { nodes, edges } = useMemo(() => {
    const main = commits.filter((c) => c.branch === "main").slice(0, 14).reverse();
    const nodes: Node[] = main.map((c, i) => ({
      id: c.id,
      position: { x: i * 120, y: 0 },
      data: { label: `${c.id.slice(0, 7)}${c.tag ? ` · ${c.tag.replace("release-", "")}` : ""}` },
      style: { fontSize: 10, padding: 4, width: 110, borderColor: c.tag ? "var(--ok)" : "var(--border)", background: "var(--card)", color: "var(--foreground)" },
    }));
    const edges: Edge[] = main.slice(1).map((c, i) => ({ id: `m${i}`, source: main[i].id, target: c.id, style: { stroke: "var(--env-production)", strokeWidth: 2 } }));
    const sandboxes = branches.filter((b) => b.env === "sandbox").slice(-8);
    sandboxes.forEach((b, i) => {
      const anchor = main.findLast((c) => c.createdAt <= b.createdAt) ?? main[0];
      const ax = (main.indexOf(anchor) || 0) * 120;
      const id = `b-${b.id}`;
      nodes.push({
        id,
        position: { x: ax + 40, y: 80 + (i % 4) * 56 },
        data: { label: `${b.name.replace("sandbox/", "")} · ${b.status}` },
        style: { fontSize: 10, padding: 4, width: 200, background: "color-mix(in oklch, var(--env-sandbox) 12%, var(--card))", borderColor: "var(--env-sandbox)", color: "var(--foreground)" },
      });
      if (anchor) edges.push({ id: `e-${b.id}`, source: anchor.id, target: id, animated: b.status === "open", style: { stroke: "var(--env-sandbox)" } });
    });
    return { nodes, edges };
  }, [branches, commits]);
  return (
    <div className="h-[340px] rounded-xl border bg-card" aria-label="Branch graph">
      <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}>
        <Background gap={20} size={1} />
      </ReactFlow>
    </div>
  );
}
