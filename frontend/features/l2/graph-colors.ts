import type { NodeType } from "@/contracts";

/** Node colours shared by the 2D and 3D graph canvases and the legend. Kept apart so the legend does not pull Sigma into the page bundle. */
export const TYPE_COLOR: Record<NodeType, string> = {
  agent: "#8b5cf6",
  skill: "#6366f1",
  tool: "#10b981",
  policy: "#f59e0b",
  security: "#ef4444",
  fact: "#0ea5e9",
  document: "#64748b",
  template: "#14b8a6",
  sensor: "#ec4899",
};
