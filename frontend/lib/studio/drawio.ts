// Exports a workflow as a draw.io (diagrams.net) diagram: same layout and colours as the in-app view.
import type { WorkflowDetail } from "@/contracts";
import { KIND_LABEL } from "./spec";
import { KIND_COLOR, NODE_H, NODE_W, layout, type Highlight } from "./graph";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function toDrawioXml(detail: WorkflowDetail, hl?: Highlight): string {
  const { nodes, edges } = layout(detail);
  const cellId = new Map(nodes.map((n, i) => [n.id, `n${i}`]));
  const cells: string[] = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>'];
  cells.push(`<mxCell id="title" value="${esc(detail.workflow.name)} · v${detail.workflow.version}" style="text;fontSize=16;fontStyle=1;align=left;" vertex="1" parent="1"><mxGeometry x="0" y="-60" width="600" height="30" as="geometry"/></mxCell>`);
  for (const n of nodes) {
    const color = KIND_COLOR[n.item.kind];
    const stroke = hl?.broken.has(n.id) ? "#dc2626" : hl?.target === n.id ? "#4f46e5" : hl?.affected.has(n.id) ? "#d97706" : color;
    const width = hl && (hl.target === n.id || hl.broken.has(n.id) || hl.affected.has(n.id)) ? 3 : 1.5;
    const label = `${esc(KIND_LABEL[n.item.kind].toUpperCase())}&lt;br&gt;&lt;b&gt;${esc(n.item.name)}&lt;/b&gt;${n.sharedBy > 1 ? `&lt;br&gt;shared by ${n.sharedBy} workflows` : ""}`;
    const dashed = n.item.status !== "active" ? "dashed=1;" : "";
    cells.push(`<mxCell id="${cellId.get(n.id)}" value="${label}" style="rounded=1;whiteSpace=wrap;html=1;fontSize=11;fillColor=#ffffff;strokeColor=${stroke};strokeWidth=${width};${dashed}" vertex="1" parent="1"><mxGeometry x="${n.x}" y="${n.y}" width="${NODE_W}" height="${NODE_H}" as="geometry"/></mxCell>`);
  }
  edges.forEach((e, i) => {
    const style = `edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;fontSize=9;endArrow=block;strokeColor=${e.faint ? "#cbd5e1" : "#64748b"};${e.faint ? "dashed=1;" : ""}`;
    cells.push(`<mxCell id="e${i}" value="${esc(e.rel)}" style="${style}" edge="1" parent="1" source="${cellId.get(e.source)}" target="${cellId.get(e.target)}"><mxGeometry relative="1" as="geometry"/></mxCell>`);
  });
  return `<mxfile host="finebrain"><diagram name="${esc(detail.workflow.name)}" id="${esc(detail.workflow.id)}"><mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" pageWidth="1600" pageHeight="1000"><root>${cells.join("")}</root></mxGraphModel></diagram></mxfile>`;
}

/** draw.io reads "#R" followed by base64 of deflate-raw compressed, URI encoded XML. */
export async function drawioUrl(xml: string): Promise<string> {
  const bytes = new TextEncoder().encode(encodeURIComponent(xml));
  const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate-raw"));
  const buf = new Uint8Array(await new Response(stream).arrayBuffer());
  let bin = "";
  for (const b of buf) bin += String.fromCharCode(b);
  return `https://app.diagrams.net/#R${encodeURIComponent(btoa(bin))}`;
}

export function downloadDrawio(xml: string, name: string) {
  const url = URL.createObjectURL(new Blob([xml], { type: "application/xml" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.drawio`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
