"use client";

import { useReducedMotion } from "motion/react";
import { ChevronLeft, ChevronRight, LayoutGrid, Maximize2, Minus, Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { BrainMap as BrainMapData, MemberKind } from "@/contracts";
import { Button } from "@/components/ui/button";
import { money, pct, usd } from "@/lib/format";
import { KIND_COLOR } from "@/lib/studio/graph";
import { KIND_PLURAL, MEMBER_ORDER } from "@/lib/studio/spec";
import { cn } from "@/lib/utils";

// Clusters sit in a ring around the brain's live core; each branches into its workflows, and each workflow into its parts.
// Click a cluster to fly into it: the cluster stands at the bottom and its workflows fan out above, like a tree.

export type MapSelection = { kind: "cluster"; id: string } | { kind: "workflow"; id: string } | { kind: "item"; id: string; workflowId: string };

export const CLUSTER_PALETTE = ["#2dd4bf", "#a78bfa", "#f472b6", "#fbbf24", "#60a5fa", "#34d399", "#fb7185", "#c084fc"];

type Cluster = BrainMapData["clusters"][number];
type Wf = BrainMapData["workflows"][number];
type Item = Wf["items"][number];
type P = { x: number; y: number };
type ItemNode = P & { key: string; item: Item; wf: Wf; prev: P };
type WfNode = P & { wf: Wf; angle: number };
type ClusterNode = { c: Cluster; color: string; hub: P; label: P; anchor: "start" | "middle" | "end"; angle: number; span: number; fan: number; orbits: number[]; wfs: WfNode[]; items: ItemNode[] };

/** The natural box of the focused view: hub at (0, 330), workflows on an arc above it. */
const VB = { x: -600, y: -230, w: 1200, h: 620 };
const R_HUB = 200;

const polar = (r: number, a: number): P => ({ x: Math.cos(a) * r, y: Math.sin(a) * r });

/** An orbit arc of radius r around c, from angle a0 to a1 (clockwise). */
function orbitArc(c: P, r: number, a0: number, a1: number) {
  const s0 = { x: c.x + Math.cos(a0) * r, y: c.y + Math.sin(a0) * r };
  const s1 = { x: c.x + Math.cos(a1) * r, y: c.y + Math.sin(a1) * r };
  return `M ${s0.x} ${s0.y} A ${r} ${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${s1.x} ${s1.y}`;
}

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 6;
type View = { x: number; y: number; k: number };
const IDENTITY: View = { x: 0, y: 0, k: 1 };

function rng(seed: number) {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let x = Math.imul(t ^ (t >>> 15), 1 | t);
    x ^= x + Math.imul(x ^ (x >>> 7), 61 | x);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

/** Parts of a workflow in the studio's order, split into a few chains so each workflow reads as a small tree. */
function branches(wf: Wf, max = 3) {
  const ordered = MEMBER_ORDER.flatMap((k) => wf.items.filter((i) => i.kind === k));
  const k = Math.max(1, Math.min(max, Math.ceil(ordered.length / 5)));
  const size = Math.ceil(ordered.length / k);
  return Array.from({ length: k }, (_, i) => ordered.slice(i * size, (i + 1) * size)).filter((b) => b.length);
}

function overviewLayout(map: BrainMapData): ClusterNode[] {
  const byCluster = new Map(map.clusters.map((c) => [c.id, map.workflows.filter((w) => w.clusterId === c.id).sort((a, b) => a.name.localeCompare(b.name))]));
  // Every cluster gets its own slice of the ring; bigger clusters get a little more room, never the whole ring.
  const weight = (c: Cluster) => 1 + Math.min(byCluster.get(c.id)!.length, 14) * 0.14;
  const total = map.clusters.reduce((s, c) => s + weight(c), 0);
  let start = -Math.PI / 2 - (Math.PI * 2 * weight(map.clusters[0])) / total / 2;
  return map.clusters.map((c, ci) => {
    const span = (Math.PI * 2 * weight(c)) / total;
    const angle = start + span / 2;
    start += span;
    const hub = polar(R_HUB, angle);
    const wfs = byCluster.get(c.id)!;
    const m = wfs.length;
    // The cluster's own fan opens outward from its hub, like a tree growing away from the core.
    const fan = Math.min(span * 0.92, Math.max(0.9, m * 0.17), 2.2);
    const wfNodes: WfNode[] = wfs.map((wf, j) => {
      const a = m === 1 ? angle : angle - fan / 2 + (j * fan) / (m - 1);
      const r = 92 + (m > 5 ? (j % 2) * 34 : 0);
      return { wf, angle: a, x: hub.x + Math.cos(a) * r, y: hub.y + Math.sin(a) * r };
    });
    const items: ItemNode[] = [];
    for (const w of wfNodes) {
      const bs = branches(w.wf);
      const width = Math.min(m > 1 ? (fan / (m - 1)) * 0.9 : 0.6, 0.6);
      const base = Math.hypot(w.x - hub.x, w.y - hub.y);
      bs.forEach((b, bi) => {
        const ba = w.angle + (bs.length > 1 ? (bi - (bs.length - 1) / 2) * (width / bs.length) : 0);
        let prev: P = { x: w.x, y: w.y };
        b.forEach((item, t) => {
          const r = base + 24 + t * 17;
          const jitter = (t % 2 ? 1 : -1) * Math.min(0.03, width / 6);
          const p = { x: hub.x + Math.cos(ba + jitter) * r, y: hub.y + Math.sin(ba + jitter) * r };
          items.push({ key: `${w.wf.id}:${item.id}`, item, wf: w.wf, prev, ...p });
          prev = p;
        });
      });
    }
    const reach = items.length ? Math.max(...items.map((i) => Math.hypot(i.x - hub.x, i.y - hub.y))) : 20;
    const label = polar(R_HUB + reach + 34, angle);
    const cos = Math.cos(angle);
    const orbits = m === 0 ? [] : m > 5 ? [92, 126] : [92];
    return { c, color: CLUSTER_PALETTE[ci % CLUSTER_PALETTE.length], hub, label, anchor: cos > 0.35 ? "start" : cos < -0.35 ? "end" : "middle", angle, span, fan, orbits, wfs: wfNodes, items };
  });
}

/** The box everything is drawn in, labels included, so the map fills the page whatever the cluster count. */
function boundsOf(layout: ClusterNode[]) {
  let x0 = -110, y0 = -110, x1 = 110, y1 = 110;
  const add = (x: number, y: number) => {
    x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
  };
  for (const l of layout) {
    add(l.hub.x, l.hub.y);
    for (const i of l.items) add(i.x, i.y);
    const w = l.c.name.length * (l.c.status === "planned" ? 9.5 : 12.5);
    const lx = l.anchor === "start" ? l.label.x : l.anchor === "end" ? l.label.x - w : l.label.x - w / 2;
    add(lx, l.label.y - 18);
    add(lx + w, l.label.y + 22);
  }
  const pad = 30;
  return { x: x0 - pad, y: y0 - pad, w: x1 - x0 + pad * 2, h: y1 - y0 + pad * 2 };
}

/** The flown-into view of one cluster: hub at the bottom, workflows on an arc above, parts branching outward. */
function focusLayout(cn: ClusterNode) {
  const hub: P = { x: 0, y: 330 };
  const m = Math.max(cn.wfs.length, 1);
  const arc = Math.PI * 0.92;
  const startA = -Math.PI / 2 - arc / 2;
  const wfs = cn.wfs.map((w, j) => {
    const a = m === 1 ? -Math.PI / 2 : startA + (j * arc) / (m - 1);
    const r = 205 + (m > 6 ? (j % 2) * 62 : 0);
    return { wf: w.wf, angle: a, x: hub.x + Math.cos(a) * r, y: hub.y + Math.sin(a) * r };
  });
  const items: ItemNode[] = [];
  for (const w of wfs) {
    const bs = branches(w.wf);
    const width = Math.min((arc / m) * 0.9, 0.9);
    const base = Math.hypot(w.x - hub.x, w.y - hub.y);
    bs.forEach((b, bi) => {
      const ba = w.angle + (bs.length > 1 ? (bi - (bs.length - 1) / 2) * (width / bs.length) : 0);
      let prev: P = { x: w.x, y: w.y };
      b.forEach((item, t) => {
        const r = base + 46 + t * 30;
        const p = { x: hub.x + Math.cos(ba) * r, y: hub.y + Math.sin(ba) * r };
        items.push({ key: `${w.wf.id}:${item.id}`, item, wf: w.wf, prev, ...p });
        prev = p;
      });
    });
  }
  // Place each workflow label where it collides with no other label: right, left, above, then below its node.
  const placed: { x0: number; y0: number; x1: number; y1: number }[] = [{ x0: hub.x - 30, y0: hub.y - 30, x1: hub.x + 30, y1: hub.y + 30 }];
  const labels = wfs.map((w) => {
    const width = w.wf.name.length * 7 + 6;
    const tries: { dx: number; dy: number; anchor: "start" | "end" | "middle" }[] = w.x < hub.x - 20
      ? [{ dx: -15, dy: 4, anchor: "end" }, { dx: 0, dy: -17, anchor: "middle" }, { dx: 0, dy: 26, anchor: "middle" }, { dx: 15, dy: 4, anchor: "start" }]
      : w.x > hub.x + 20
        ? [{ dx: 15, dy: 4, anchor: "start" }, { dx: 0, dy: -17, anchor: "middle" }, { dx: 0, dy: 26, anchor: "middle" }, { dx: -15, dy: 4, anchor: "end" }]
        : [{ dx: 0, dy: -17, anchor: "middle" }, { dx: 15, dy: 4, anchor: "start" }, { dx: -15, dy: 4, anchor: "end" }, { dx: 0, dy: 26, anchor: "middle" }];
    const box = (t: (typeof tries)[number]) => {
      const x = w.x + t.dx;
      const x0 = t.anchor === "start" ? x : t.anchor === "end" ? x - width : x - width / 2;
      return { x0, y0: w.y + t.dy - 12, x1: x0 + width, y1: w.y + t.dy + 3 };
    };
    const hit = (b: { x0: number; y0: number; x1: number; y1: number }) => placed.some((p) => b.x0 < p.x1 && b.x1 > p.x0 && b.y0 < p.y1 && b.y1 > p.y0);
    const pick = tries.find((t) => !hit(box(t))) ?? tries[0];
    placed.push(box(pick));
    return { x: w.x + pick.dx, y: w.y + pick.dy, anchor: pick.anchor };
  });
  const orbits = { radii: m > 6 ? [205, 267] : [205], from: startA - 0.18, to: startA + arc + 0.18 };
  return { hub, wfs, items, labels, orbits };
}

function onKey(fn: () => void) {
  return (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fn();
    }
  };
}

export function BrainMapView({ map, currency, focusId, selection, onFocus, onSelect }: { map: BrainMapData; currency: string; focusId: string | null; selection: MapSelection | null; onFocus: (clusterId: string | null) => void; onSelect: (s: MapSelection | null) => void }) {
  const reduce = useReducedMotion();
  const layout = useMemo(() => overviewLayout(map), [map]);
  const vb = useMemo(() => boundsOf(layout), [layout]);
  const outerOrbit = useMemo(() => Math.max(R_HUB + 140, ...layout.flatMap((l) => l.items.map((i) => Math.hypot(i.x, i.y) + 14))), [layout]);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [hoverWf, setHoverWf] = useState<string | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number; id: string } | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Pan and zoom. The view belongs to the cluster it was set for, so flying in or out starts from a fitted view.
  const [vs, setVs] = useState<{ f: string | null; v: View; smooth: boolean }>({ f: null, v: IDENTITY, smooth: false });
  const view = vs.f === focusId ? vs.v : IDENTITY;
  const setView = useCallback((fn: (v: View) => View, smooth = false) => setVs((cur) => ({ f: focusId, v: fn(cur.f === focusId ? cur.v : IDENTITY), smooth })), [focusId]);
  const [dragging, setDragging] = useState(false);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ sx: number; sy: number; v: View; moved: boolean; d0: number; mid: P | null } | null>(null);
  const suppressClick = useRef(false);

  const toUser = useCallback((clientX: number, clientY: number): P => {
    const ctm = svgRef.current?.getScreenCTM();
    if (!ctm) return { x: 0, y: 0 };
    const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }, []);
  const zoomAt = useCallback(
    (u: P, factor: number, smooth = false) =>
      setView((v) => {
        const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, v.k * factor));
        const f = k / v.k;
        return { k, x: u.x - (u.x - v.x) * f, y: u.y - (u.y - v.y) * f };
      }, smooth),
    [setView],
  );
  const zoomCenter = (factor: number) => zoomAt({ x: vb.x + vb.w / 2, y: vb.y + vb.h / 2 }, factor, true);

  // Wheel and trackpad pinch zoom around the cursor. Needs a non-passive listener to keep the page from scrolling.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const speed = e.ctrlKey ? 0.01 : 0.0018;
      zoomAt(toUser(e.clientX, e.clientY), Math.exp(-e.deltaY * speed));
      setTip(null);
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [zoomAt, toUser]);

  const pxPerUnit = () => svgRef.current?.getScreenCTM()?.a ?? 1;
  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const pts = [...pointers.current.values()];
    gesture.current = {
      sx: e.clientX, sy: e.clientY, v: view, moved: false,
      d0: pts.length === 2 ? Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) : 0,
      mid: pts.length === 2 ? toUser((pts[0].x + pts[1].x) / 2, (pts[0].y + pts[1].y) / 2) : null,
    };
  };
  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const g = gesture.current;
    if (!g || !pointers.current.has(e.pointerId)) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const pts = [...pointers.current.values()];
    if (pts.length === 2 && g.d0 && g.mid) {
      const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, g.v.k * (d / g.d0)));
      const f = k / g.v.k;
      g.moved = true;
      setView(() => ({ k, x: g.mid!.x - (g.mid!.x - g.v.x) * f, y: g.mid!.y - (g.mid!.y - g.v.y) * f }));
      return;
    }
    const dx = e.clientX - g.sx;
    const dy = e.clientY - g.sy;
    if (!g.moved && Math.hypot(dx, dy) < 4) return;
    if (!g.moved) {
      g.moved = true;
      setDragging(true);
      setTip(null);
      svgRef.current?.setPointerCapture(e.pointerId);
    }
    const u = pxPerUnit();
    setView(() => ({ ...g.v, x: g.v.x + dx / u, y: g.v.y + dy / u }));
  };
  const endPointer = (e: React.PointerEvent<SVGSVGElement>) => {
    pointers.current.delete(e.pointerId);
    if (gesture.current?.moved) suppressClick.current = true;
    if (pointers.current.size === 0) {
      gesture.current = null;
      setDragging(false);
    }
  };

  const focused = layout.find((l) => l.c.id === focusId) ?? null;
  const focus = useMemo(() => (focused ? focusLayout(focused) : null), [focused]);
  const selectedWf = selection?.kind === "workflow" ? selection.id : selection?.kind === "item" ? selection.workflowId : null;
  const activeWf = hoverWf ?? selectedWf;
  const [hoverItem, setHoverItem] = useState<string | null>(null);

  // Labels for the lit workflow's parts, kept only where they do not collide; the rest show on hover.
  const itemLabels = useMemo(() => {
    const out = new Set<string>();
    if (!focus || !activeWf) return out;
    const boxes = [...focus.labels.map((l, i) => {
      const w = focus.wfs[i].wf.name.length * 7 + 6;
      const x0 = l.anchor === "start" ? l.x : l.anchor === "end" ? l.x - w : l.x - w / 2;
      return { x0, y0: l.y - 12, x1: x0 + w, y1: l.y + 3 };
    })];
    for (const it of focus.items.filter((i) => i.wf.id === activeWf)) {
      const w = it.item.name.length * 5.8 + 4;
      const left = it.x < focus.hub.x;
      const x0 = left ? it.x - 9 - w : it.x + 9;
      const b = { x0, y0: it.y - 7, x1: x0 + w, y1: it.y + 5 };
      if (!boxes.some((p) => b.x0 < p.x1 && b.x1 > p.x0 && b.y0 < p.y1 && b.y1 > p.y0)) {
        boxes.push(b);
        out.add(it.key);
      }
    }
    return out;
  }, [focus, activeWf]);

  const fly = useCallback(
    (id: string | null) => {
      onFocus(id);
      setVs({ f: id, v: IDENTITY, smooth: false });
      setHoverId(null);
      setTip(null);
      setHoverWf(null);
      onSelect(null);
    },
    [onFocus, onSelect],
  );
  const step = (d: 1 | -1) => {
    const i = layout.findIndex((l) => l.c.id === focusId);
    fly(layout[(i + d + layout.length) % layout.length].c.id);
  };

  useEffect(() => {
    const esc = (e: globalThis.KeyboardEvent) => e.key === "Escape" && focusId && fly(null);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [focusId, fly]);

  const showTip = (id: string, p: P) => {
    const svg = svgRef.current;
    const box = boxRef.current;
    if (!svg || !box) return;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const pt = new DOMPoint(p.x * view.k + view.x, p.y * view.k + view.y).matrixTransform(ctm);
    const r = box.getBoundingClientRect();
    setTip({ id, x: pt.x - r.left, y: pt.y - r.top });
  };

  // The overview flies toward the focused hub as the focus view grows out of it.
  const ovTransform = focused ? `translate(${-focused.hub.x * 2.4}px, ${-focused.hub.y * 2.4}px) scale(2.4)` : "translate(0px, 0px) scale(1)";
  const particles = useMemo(() => {
    const r = rng(map.workflows.length * 7919 + map.clusters.length);
    return Array.from({ length: 130 }, (_, i) => {
      const a = r() * Math.PI * 2;
      const d = Math.pow(r(), 0.6) * 74;
      return { x: Math.cos(a) * d, y: Math.sin(a) * d, s: 0.8 + r() * 1.8, c: CLUSTER_PALETTE[i % layout.length], delay: r() * 2.6 };
    });
  }, [map.workflows.length, map.clusters.length, layout.length]);

  const tipCluster = tip ? layout.find((l) => l.c.id === tip.id) : null;
  const totalWf = map.workflows.length;

  return (
    <div ref={boxRef} className="map-surface relative h-full w-full overflow-hidden" onMouseLeave={() => { setHoverId(null); setTip(null); }}>
      {focused && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center overflow-hidden" aria-hidden>
          <span className="select-none whitespace-nowrap text-[clamp(56px,11vw,180px)] font-semibold uppercase tracking-[0.2em] opacity-[0.06]" style={{ color: "var(--map-label)" }}>
            {focused.c.name}
          </span>
        </div>
      )}
      <svg
        ref={svgRef}
        viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
        preserveAspectRatio="xMidYMid meet"
        className={cn("absolute inset-0 h-full w-full touch-none select-none", dragging ? "cursor-grabbing" : "cursor-grab")}
        role="group"
        aria-label={`Brain map: ${map.clusters.length} clusters and ${totalWf} workflows. Drag to move, scroll to zoom, pick a cluster to open it.`}
        data-testid="brain-map"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPointer}
        onPointerCancel={endPointer}
        onClickCapture={(e) => {
          if (suppressClick.current) {
            suppressClick.current = false;
            e.stopPropagation();
            e.preventDefault();
          }
        }}
      >
        <g style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`, transformBox: "view-box", transformOrigin: "0 0", transition: vs.smooth && !dragging ? "transform 260ms cubic-bezier(0.22, 1, 0.36, 1)" : "none" }} data-testid="map-viewport">
        {/* ---------------- overview ring ---------------- */}
        <g className="map-layer" style={{ transform: ovTransform, opacity: focused ? 0 : 1, pointerEvents: focused ? "none" : undefined }} aria-hidden={!!focused}>
          {/* live core */}
          <g aria-hidden>
            {layout.filter((l) => l.c.status === "active").map((l) => (
              <line key={`core-${l.c.id}`} x1={0} y1={0} x2={l.hub.x} y2={l.hub.y} stroke={l.color} strokeOpacity={0.35} strokeWidth={1} className={reduce ? undefined : "map-flow"} />
            ))}
            {particles.map((p, i) => (
              <circle key={i} cx={p.x} cy={p.y} r={p.s} fill={p.c} className={reduce ? undefined : "map-twinkle"} style={{ animationDelay: `${p.delay}s` }} opacity={0.75} />
            ))}
          </g>
          {/* orbits: the core, the ring every cluster hub sits on, and the outer edge of the brain */}
          <g aria-hidden pointerEvents="none" fill="none" stroke="var(--map-line)">
            <circle r={96} strokeDasharray="2 7" />
            <circle r={R_HUB} strokeWidth={1.3} strokeDasharray="5 7" />
            <circle r={outerOrbit} strokeDasharray="2 10" strokeOpacity={0.7} />
          </g>
          {layout.map((l) => {
            const dim = hoverId && hoverId !== l.c.id;
            const lit = hoverId === l.c.id;
            const planned = l.c.status === "planned";
            const inner = 120;
            const outer = 400;
            const a0 = l.angle - l.span / 2;
            const a1 = l.angle + l.span / 2;
            const big = l.span > Math.PI ? 1 : 0;
            const wedge = `M ${polar(inner, a0).x} ${polar(inner, a0).y} L ${polar(outer, a0).x} ${polar(outer, a0).y} A ${outer} ${outer} 0 ${big} 1 ${polar(outer, a1).x} ${polar(outer, a1).y} L ${polar(inner, a1).x} ${polar(inner, a1).y} A ${inner} ${inner} 0 ${big} 0 ${polar(inner, a0).x} ${polar(inner, a0).y} Z`;
            return (
              <g key={l.c.id} style={{ opacity: dim ? 0.22 : 1, transition: "opacity 300ms" }} onMouseEnter={() => { setHoverId(l.c.id); showTip(l.c.id, l.hub); }}>
                <path d={wedge} fill="transparent" onClick={() => fly(l.c.id)} className="cursor-pointer" />
                <g aria-hidden pointerEvents="none">
                  {l.orbits.map((r) => (
                    <path key={`orbit-${r}`} d={orbitArc(l.hub, r, l.angle - l.fan / 2 - 0.3, l.angle + l.fan / 2 + 0.3)} fill="none" stroke={lit ? l.color : "var(--map-line)"} strokeOpacity={lit ? 0.7 : 1} strokeDasharray="3 6" />
                  ))}
                  {l.wfs.map((w) => (
                    <line key={w.wf.id} x1={l.hub.x} y1={l.hub.y} x2={w.x} y2={w.y} stroke={lit ? l.color : "var(--map-line)"} strokeWidth={lit ? 1.2 : 0.9} />
                  ))}
                  {l.items.map((it) => (
                    <line key={`e-${it.key}`} x1={it.prev.x} y1={it.prev.y} x2={it.x} y2={it.y} stroke="var(--map-line)" strokeWidth={0.7} />
                  ))}
                  {l.items.map((it) => (
                    <circle key={it.key} cx={it.x} cy={it.y} r={it.item.kind === "tool" && it.item.shared ? 2.6 : 2.1} fill={lit ? KIND_COLOR[it.item.kind] : "var(--map-node)"} opacity={it.item.status === "active" ? 0.9 : 0.4} />
                  ))}
                  {l.wfs.map((w) => (
                    <circle key={`n-${w.wf.id}`} cx={w.x} cy={w.y} r={4.2} fill="var(--map-node)" stroke={w.wf.health.breaks ? "#ef4444" : lit ? l.color : "none"} strokeWidth={1.4} />
                  ))}
                </g>
                {!planned && !reduce && <circle cx={l.hub.x} cy={l.hub.y} r={11} fill="none" stroke={l.color} className="map-pulse" aria-hidden pointerEvents="none" />}
                <g
                  role="button"
                  tabIndex={focused ? -1 : 0}
                  aria-label={`${l.c.name}: ${l.wfs.length} workflow${l.wfs.length === 1 ? "" : "s"}${planned ? ", planned" : ""}. Open cluster`}
                  className="cursor-pointer outline-none [&:focus-visible>circle.ring]:opacity-100"
                  onClick={() => fly(l.c.id)}
                  onKeyDown={onKey(() => fly(l.c.id))}
                  onFocus={() => { setHoverId(l.c.id); showTip(l.c.id, l.hub); }}
                  onBlur={() => { setHoverId(null); setTip(null); }}
                >
                  <circle cx={l.hub.x} cy={l.hub.y} r={22} fill="transparent" />
                  <circle className="ring opacity-0" cx={l.hub.x} cy={l.hub.y} r={17} fill="none" stroke="var(--ring)" strokeWidth={2} />
                  <circle cx={l.hub.x} cy={l.hub.y} r={11} fill="var(--map-bg-2)" stroke={l.color} strokeWidth={2} strokeDasharray={planned ? "3 3" : undefined} />
                  <circle cx={l.hub.x} cy={l.hub.y} r={4} fill={l.color} opacity={planned ? 0.4 : 1} />
                </g>
                <g pointerEvents="none">
                  <text x={l.label.x} y={l.label.y} textAnchor={l.anchor} fontSize={(planned ? 12 : 15) + (lit ? 2 : 0)} letterSpacing={planned ? "0.12em" : "0.18em"} fontWeight={600} fill={lit ? l.color : "var(--map-label)"} style={{ textTransform: "uppercase", transition: "fill 200ms" }}>
                    {l.c.name.toUpperCase()}
                  </text>
                  <text x={l.label.x} y={l.label.y + 17} textAnchor={l.anchor} fontSize={10.5} letterSpacing="0.08em" fill="var(--map-sub)">
                    {planned ? "planned" : `${l.wfs.length} workflows · ${l.items.length} parts`}
                  </text>
                </g>
              </g>
            );
          })}
        </g>

        {/* ---------------- focused cluster ---------------- */}
        {focused && focus && (
          <g style={{ transform: `translateX(${selection ? vb.w * 0.12 : 0}px)`, transition: "transform 500ms cubic-bezier(0.22, 1, 0.36, 1)" }}>
          <g transform={(() => {
            const k = Math.min(vb.w / VB.w, vb.h / VB.h);
            return `translate(${vb.x + vb.w / 2 - (VB.x + VB.w / 2) * k} ${vb.y + vb.h / 2 - (VB.y + VB.h / 2) * k}) scale(${k})`;
          })()}>
          <g className="map-enter" key={focused.c.id}>
            {focus.orbits.radii.map((r) => (
              <path key={`fo-${r}`} d={orbitArc(focus.hub, r, focus.orbits.from, focus.orbits.to)} fill="none" stroke={focused.color} strokeOpacity={0.35} strokeWidth={1.2} strokeDasharray="4 7" aria-hidden />
            ))}
            {focus.wfs.map((w) => (
              <line key={`fe-${w.wf.id}`} x1={focus.hub.x} y1={focus.hub.y} x2={w.x} y2={w.y} stroke={activeWf === w.wf.id ? focused.color : "var(--map-line)"} strokeWidth={activeWf === w.wf.id ? 2 : 1.2} />
            ))}
            {focus.items.map((it) => {
              const on = !activeWf || activeWf === it.wf.id;
              return <line key={`fi-${it.key}`} x1={it.prev.x} y1={it.prev.y} x2={it.x} y2={it.y} stroke={activeWf === it.wf.id ? focused.color : "var(--map-line)"} strokeOpacity={on ? 1 : 0.35} strokeWidth={1} />;
            })}
            {focus.items.map((it) => {
              const on = !activeWf || activeWf === it.wf.id;
              const sel = selection?.kind === "item" && selection.id === it.item.id && selection.workflowId === it.wf.id;
              const left = it.x < focus.hub.x;
              return (
                <g
                  key={`fn-${it.key}`}
                  role="button"
                  tabIndex={0}
                  aria-label={`${it.item.name}, ${it.item.kind} in ${it.wf.name}`}
                  className="cursor-pointer outline-none"
                  style={{ opacity: on ? 1 : 0.3, transition: "opacity 250ms" }}
                  onClick={() => onSelect({ kind: "item", id: it.item.id, workflowId: it.wf.id })}
                  onKeyDown={onKey(() => onSelect({ kind: "item", id: it.item.id, workflowId: it.wf.id }))}
                  onMouseEnter={() => { setHoverWf(it.wf.id); setHoverItem(it.key); }}
                  onMouseLeave={() => { setHoverWf(null); setHoverItem(null); }}
                >
                  <title>{`${it.item.name} (${it.item.kind})`}</title>
                  <circle cx={it.x} cy={it.y} r={12} fill="transparent" />
                  <circle cx={it.x} cy={it.y} r={sel ? 7 : 5} fill="var(--map-node)" stroke={KIND_COLOR[it.item.kind as MemberKind]} strokeWidth={sel ? 3 : 2} strokeDasharray={it.item.status === "active" ? undefined : "2 2"} />
                  {(itemLabels.has(it.key) || sel || hoverItem === it.key) && (
                    <text x={it.x + (left ? -9 : 9)} y={it.y + 3.5} textAnchor={left ? "end" : "start"} fontSize={10.5} fill="var(--map-label)" paintOrder="stroke" stroke="var(--map-bg-2)" strokeWidth={3}>
                      {it.item.name}
                    </text>
                  )}
                </g>
              );
            })}
            {focus.wfs.map((w, wi) => {
              const sel = selectedWf === w.wf.id;
              const lab = focus.labels[wi];
              return (
                <g
                  key={`fw-${w.wf.id}`}
                  role="button"
                  tabIndex={0}
                  aria-label={`${w.wf.name} workflow, ${w.wf.items.length} parts${w.wf.health.breaks ? `, ${w.wf.health.breaks} broken` : ""}`}
                  className="cursor-pointer outline-none [&:focus-visible>circle.ring]:opacity-100"
                  onClick={() => onSelect({ kind: "workflow", id: w.wf.id })}
                  onKeyDown={onKey(() => onSelect({ kind: "workflow", id: w.wf.id }))}
                  onMouseEnter={() => setHoverWf(w.wf.id)}
                  onMouseLeave={() => setHoverWf(null)}
                >
                  <circle cx={w.x} cy={w.y} r={16} fill="transparent" />
                  <circle className="ring opacity-0" cx={w.x} cy={w.y} r={15} fill="none" stroke="var(--ring)" strokeWidth={2} />
                  <circle cx={w.x} cy={w.y} r={sel ? 11 : 9} fill="var(--map-bg-2)" stroke={w.wf.health.breaks ? "#ef4444" : focused.color} strokeWidth={sel ? 3.5 : 2.5} />
                  <circle cx={w.x} cy={w.y} r={3.2} fill={focused.color} />
                  <text x={lab.x} y={lab.y} textAnchor={lab.anchor} fontSize={12.5} fontWeight={600} fill="var(--map-label)" paintOrder="stroke" stroke="var(--map-bg-2)" strokeWidth={4}>
                    {w.wf.name}
                  </text>
                </g>
              );
            })}
            <g role="button" tabIndex={0} aria-label={`${focused.c.name} details`} className="cursor-pointer outline-none" onClick={() => onSelect({ kind: "cluster", id: focused.c.id })} onKeyDown={onKey(() => onSelect({ kind: "cluster", id: focused.c.id }))}>
              {!reduce && <circle cx={focus.hub.x} cy={focus.hub.y} r={11} fill="none" stroke={focused.color} className="map-pulse" />}
              <circle cx={focus.hub.x} cy={focus.hub.y} r={24} fill="var(--map-bg-2)" stroke={focused.color} strokeWidth={3} />
              <circle cx={focus.hub.x} cy={focus.hub.y} r={8} fill={focused.color} />
            </g>
            {focus.wfs.length === 0 && (
              <text x={0} y={200} textAnchor="middle" fontSize={15} fill="var(--map-sub)">
                Planned cluster. No workflows yet; add one in Workflow Studio.
              </text>
            )}
          </g>
          </g>
          </g>
        )}
        </g>
      </svg>

      {/* hover card with the cluster's live numbers */}
      {tip && tipCluster && !focused && (
        <div className="pointer-events-none absolute z-10 w-56 -translate-x-1/2 rounded-xl border bg-popover/95 p-3 text-xs shadow-lg backdrop-blur" style={{ left: tip.x, top: tip.y + 26 }} role="tooltip">
          <div className="mb-1.5 flex items-center gap-1.5 font-semibold">
            <span className="size-2 rounded-full" style={{ background: tipCluster.color }} aria-hidden />
            {tipCluster.c.name}
          </div>
          {tipCluster.c.kpi ? (
            <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5">
              <dt className="text-muted-foreground">Autonomy</dt><dd className="tabular">{pct(tipCluster.c.kpi.autonomyRate)}</dd>
              <dt className="text-muted-foreground">Escalations</dt><dd className="tabular">{pct(tipCluster.c.kpi.escalationRate, 1)}</dd>
              <dt className="text-muted-foreground">Runs, 24h</dt><dd className="tabular">{tipCluster.c.kpi.runs24h}</dd>
              <dt className="text-muted-foreground">Money at stake</dt><dd className="tabular">{money(tipCluster.c.kpi.moneyAtStakeMinor, currency, { compact: true })}</dd>
              <dt className="text-muted-foreground">Cost per task</dt><dd className="tabular">{usd(tipCluster.c.kpi.costPerResolvedUsd)}</dd>
              <dt className="text-muted-foreground">Open risks</dt><dd className="tabular">{tipCluster.c.kpi.openRisks}</dd>
              <dt className="text-muted-foreground">Health</dt><dd className="tabular">{tipCluster.c.health}</dd>
            </dl>
          ) : (
            <p className="text-muted-foreground">Planned. Plugs in the same way as the active clusters once its sensors connect.</p>
          )}
          <p className="mt-1.5 text-[10px] text-muted-foreground">{tipCluster.wfs.length} workflows. Click to open.</p>
        </div>
      )}

      {/* pan and zoom controls */}
      <div className="absolute bottom-10 left-3 flex flex-col overflow-hidden rounded-xl border bg-card/90 shadow-sm backdrop-blur" role="group" aria-label="Zoom">
        <Button size="icon-sm" variant="ghost" className="rounded-none" onClick={() => zoomCenter(1.35)} aria-label="Zoom in" disabled={view.k >= MAX_ZOOM}>
          <Plus />
        </Button>
        <Button size="icon-sm" variant="ghost" className="rounded-none border-y" onClick={() => zoomCenter(1 / 1.35)} aria-label="Zoom out" disabled={view.k <= MIN_ZOOM}>
          <Minus />
        </Button>
        <Button size="icon-sm" variant="ghost" className="rounded-none" onClick={() => setView(() => IDENTITY, true)} aria-label="Fit to screen" disabled={view === IDENTITY}>
          <Maximize2 />
        </Button>
      </div>
      <span className="pointer-events-none absolute bottom-[136px] left-3 w-8 text-center text-[10px] tabular" style={{ color: "var(--map-sub)" }} aria-live="polite">{Math.round(view.k * 100)}%</span>

      {/* kind legend, bottom left */}
      <ul className="pointer-events-none absolute bottom-3 left-3 hidden flex-wrap gap-x-2.5 gap-y-1 text-[10px] sm:flex" style={{ color: "var(--map-sub)" }} aria-label="Legend">
        {MEMBER_ORDER.map((k) => (
          <li key={k} className="inline-flex items-center gap-1">
            <span className="size-2 rounded-full" style={{ background: KIND_COLOR[k] }} aria-hidden />
            {KIND_PLURAL[k]}
          </li>
        ))}
      </ul>

      {/* cluster stepper, like flipping through departments */}
      {focused && (
        <>
          <Button size="sm" variant="secondary" className="absolute left-3 top-14 shadow-sm" onClick={() => fly(null)}>
            <LayoutGrid /> All clusters
          </Button>
          <div className="absolute inset-x-0 bottom-3 flex items-center justify-center gap-4 sm:bottom-5">
            <Button size="icon" variant="ghost" className="rounded-full" onClick={() => step(-1)} aria-label="Previous cluster">
              <ChevronLeft />
            </Button>
            <div className="min-w-[200px] text-center">
              <div className="text-base font-semibold uppercase tracking-[0.2em]" style={{ color: focused.color }}>{focused.c.name}</div>
              <div className="text-[11px]" style={{ color: "var(--map-sub)" }}>
                {focused.c.kpi ? `${focus?.wfs.length} workflows · ${pct(focused.c.kpi.autonomyRate)} autonomous · ${focused.c.kpi.runs24h} runs today` : "planned"}
              </div>
            </div>
            <Button size="icon" variant="ghost" className="rounded-full" onClick={() => step(1)} aria-label="Next cluster">
              <ChevronRight />
            </Button>
          </div>
        </>
      )}
      <span className={cn("sr-only")} aria-live="polite">{focused ? `Opened ${focused.c.name}` : ""}</span>
    </div>
  );
}
