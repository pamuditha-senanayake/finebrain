// One layout of a workflow, shared by the in-app diagram and the draw.io export.
import type { MemberKind, StudioItem, WorkflowDetail } from "@/contracts";
import { refsOf } from "./spec";

export const KIND_COLOR: Record<MemberKind, string> = {
  sensor: "#ec4899",
  scheduler: "#14b8a6",
  agent: "#6366f1",
  skill: "#0ea5e9",
  policy: "#f59e0b",
  tool: "#10b981",
  template: "#8b5cf6",
  loop: "#f97316",
};

/** Left to right: what wakes the workflow, who works, what they do, what limits and powers it, what it reports. */
const COLUMN: Record<MemberKind, number> = { sensor: 0, scheduler: 0, agent: 1, skill: 2, policy: 3, tool: 3, template: 4, loop: 4 };
export const NODE_W = 196;
export const NODE_H = 56;
const COL_GAP = 270;
const ROW_GAP = 76;

export type FlowNode = { id: string; item: StudioItem; x: number; y: number; sharedBy: number };
export type FlowEdge = { id: string; source: string; target: string; rel: string; faint: boolean };

// Some references read better drawn the other way round, so data always flows left to right.
const FLIP = new Set(["run by", "reads", "fed by"]);
const FLIP_LABEL: Record<string, string> = { "run by": "runs", reads: "read by", "fed by": "feeds" };
const FAINT = new Set(["reads", "fed by", "wakes", "senses", "guarded by", "acts with"]);

export function layout(detail: WorkflowDetail): { nodes: FlowNode[]; edges: FlowEdge[]; width: number; height: number } {
  const sharing = new Map(detail.sharedToolUse.map((s) => [s.toolId, s.workflows.length]));
  const cols: StudioItem[][] = [[], [], [], [], []];
  const order: MemberKind[] = ["sensor", "scheduler", "agent", "skill", "policy", "tool", "template", "loop"];
  for (const k of order) for (const it of detail.items.filter((i) => i.kind === k)) cols[COLUMN[k]].push(it);
  const tallest = Math.max(...cols.map((c) => c.length), 1);
  const nodes: FlowNode[] = [];
  cols.forEach((col, ci) => {
    const offset = ((tallest - col.length) * ROW_GAP) / 2;
    col.forEach((it, ri) => nodes.push({ id: it.id, item: it, x: ci * COL_GAP, y: offset + ri * ROW_GAP, sharedBy: sharing.get(it.id) ?? 0 }));
  });
  const ids = new Set(nodes.map((n) => n.id));
  const edges: FlowEdge[] = [];
  for (const it of detail.items) {
    for (const r of refsOf(it.kind, it.fields)) {
      if (!ids.has(r.id)) continue;
      const flip = FLIP.has(r.rel);
      const source = flip ? r.id : it.id;
      const target = flip ? it.id : r.id;
      const id = `${source}->${target}`;
      if (edges.some((e) => e.id === id)) continue;
      edges.push({ id, source, target, rel: flip ? FLIP_LABEL[r.rel] : r.rel, faint: FAINT.has(r.rel) || it.kind === "loop" });
    }
  }
  return { nodes, edges, width: 4 * COL_GAP + NODE_W, height: tallest * ROW_GAP };
}

/** Items a review names, split by how they are touched, for highlighting. */
export type Highlight = { target: string | null; affected: Set<string>; broken: Set<string> };
export const NO_HIGHLIGHT: Highlight = { target: null, affected: new Set(), broken: new Set() };
