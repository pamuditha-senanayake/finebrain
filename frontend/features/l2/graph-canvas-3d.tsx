"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Graph as GraphData, NodeType } from "@/contracts";
import { TYPE_COLOR } from "./graph-canvas";

type Props = {
  data: GraphData;
  visibleTypes: Set<NodeType>;
  locked: Map<string, string>;
  lockedEdges: Set<string>;
  selected: string | null;
  onSelect: (id: string | null) => void;
  dark: boolean;
};

const TYPE_ORDER: NodeType[] = ["agent", "skill", "tool", "policy", "security", "fact", "document", "template", "sensor"];
const SPAN = 420;

function hash(s: string) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return ((h >>> 0) % 10000) / 10000;
}

/** 3D knowledge graph. The 2D layout supplies x and y; each node type sits on its own depth layer so the kinds read as strata. Drag to orbit, scroll to zoom, right-drag to pan. */
export default function GraphCanvas3D({ data, visibleTypes, locked, lockedEdges, selected, onSelect, dark }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const label = useRef<HTMLDivElement>(null);
  const hover = useRef<HTMLDivElement>(null);
  const live = useRef({ visibleTypes, locked, lockedEdges, selected, onSelect });
  const api = useRef<{ refresh: () => void } | null>(null);

  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const nodes = data.nodes;
    const index = new Map(nodes.map((n, i) => [n.id, i]));
    const degree = new Float32Array(nodes.length);
    for (const e of data.edges) {
      const a = index.get(e.source);
      const b = index.get(e.target);
      if (a !== undefined && b !== undefined) {
        degree[a]++;
        degree[b]++;
      }
    }
    let maxXY = 1;
    for (const n of nodes) maxXY = Math.max(maxXY, Math.abs(n.x), Math.abs(n.y));
    const k = SPAN / maxXY;
    const layerGap = SPAN / (TYPE_ORDER.length * 1.2);
    const pos = nodes.map((n) => {
      const layer = TYPE_ORDER.indexOf(n.type) - (TYPE_ORDER.length - 1) / 2;
      return new THREE.Vector3(n.x * k, -n.y * k, layer * layerGap + (hash(n.id) - 0.5) * layerGap * 0.9);
    });
    const big = nodes.length > 600;
    const radius = (i: number) => Math.min(big ? 6 : 11, (big ? 2.2 : 4.2) + Math.sqrt(degree[i]) * (big ? 0.7 : 1.4));

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, 1, 1, 5000);
    camera.position.set(0, 160, SPAN * 3.1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxDistance = 2200;
    controls.minDistance = 40;
    scene.add(new THREE.AmbientLight(0xffffff, 1.35));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(200, 300, 400);
    scene.add(sun);

    const mesh = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 14, 10), new THREE.MeshLambertMaterial(), nodes.length);
    scene.add(mesh);
    const lineGeo = new THREE.BufferGeometry();
    const edges = data.edges.filter((e) => index.has(e.source) && index.has(e.target));
    const linePos = new Float32Array(edges.length * 6);
    const lineCol = new Float32Array(edges.length * 6);
    lineGeo.setAttribute("position", new THREE.BufferAttribute(linePos, 3));
    lineGeo.setAttribute("color", new THREE.BufferAttribute(lineCol, 3));
    const lines = new THREE.LineSegments(lineGeo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.55 }));
    scene.add(lines);

    const m = new THREE.Matrix4();
    const c = new THREE.Color();
    const baseEdge = new THREE.Color(dark ? "#4a5873" : "#94a3b8");
    const dimEdge = new THREE.Color(dark ? "#222a3b" : "#e2e8f0");
    const redEdge = new THREE.Color("#ef4444");
    const lockedNode = new THREE.Color(dark ? "#3f4657" : "#cbd5e1");

    const refresh = () => {
      const s = live.current;
      nodes.forEach((n, i) => {
        const shown = s.visibleTypes.has(n.type);
        const sel = s.selected === n.id;
        const r = shown ? radius(i) * (sel ? 1.7 : 1) : 0;
        m.compose(pos[i], new THREE.Quaternion(), new THREE.Vector3(r, r, r));
        mesh.setMatrixAt(i, m);
        mesh.setColorAt(i, s.locked.has(n.id) ? lockedNode : c.set(TYPE_COLOR[n.type]));
      });
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      edges.forEach((e, j) => {
        const a = index.get(e.source)!;
        const b = index.get(e.target)!;
        const shown = s.visibleTypes.has(nodes[a].type) && s.visibleTypes.has(nodes[b].type);
        // A hidden edge collapses to a point.
        const pa = pos[a];
        const pb = shown ? pos[b] : pos[a];
        linePos.set([pa.x, pa.y, pa.z, pb.x, pb.y, pb.z], j * 6);
        const col = s.lockedEdges.has(e.id) ? redEdge : s.selected && e.source !== s.selected && e.target !== s.selected ? dimEdge : s.selected ? c.set(TYPE_COLOR[nodes[a].type]) : baseEdge;
        lineCol.set([col.r, col.g, col.b, col.r, col.g, col.b], j * 6);
      });
      lineGeo.attributes.position.needsUpdate = true;
      lineGeo.attributes.color.needsUpdate = true;
    };
    api.current = { refresh };
    refresh();

    const resize = () => {
      const w = el.clientWidth || 1;
      const h = el.clientHeight || 1;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = `${w}px`;
      renderer.domElement.style.height = `${h}px`;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    // Picking: a click that did not drag selects the nearest node under the cursor; hover shows its name.
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const pick = (ev: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hit = ray.intersectObject(mesh)[0];
      return hit?.instanceId !== undefined ? hit.instanceId : -1;
    };
    let down: { x: number; y: number } | null = null;
    const onDown = (ev: PointerEvent) => { down = { x: ev.clientX, y: ev.clientY }; };
    const onUp = (ev: PointerEvent) => {
      if (!down || Math.hypot(ev.clientX - down.x, ev.clientY - down.y) > 5) return;
      const i = pick(ev);
      live.current.onSelect(i >= 0 ? nodes[i].id : null);
    };
    const onMove = (ev: PointerEvent) => {
      const tip = hover.current;
      if (!tip || ev.buttons) { if (tip) tip.style.display = "none"; return; }
      const i = pick(ev);
      if (i < 0) { tip.style.display = "none"; renderer.domElement.style.cursor = "grab"; return; }
      const r = renderer.domElement.getBoundingClientRect();
      tip.textContent = nodes[i].label;
      tip.style.display = "block";
      tip.style.left = `${ev.clientX - r.left + 12}px`;
      tip.style.top = `${ev.clientY - r.top + 12}px`;
      renderer.domElement.style.cursor = "pointer";
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);

    let raf = 0;
    const v = new THREE.Vector3();
    const loop = () => {
      raf = requestAnimationFrame(loop);
      controls.update();
      renderer.render(scene, camera);
      // The selected node keeps a floating name that follows it as the view moves.
      const lab = label.current;
      const sel = live.current.selected;
      const si = sel ? index.get(sel) : undefined;
      if (lab && si !== undefined && live.current.visibleTypes.has(nodes[si].type)) {
        v.copy(pos[si]).project(camera);
        lab.style.display = v.z < 1 ? "block" : "none";
        lab.textContent = nodes[si].label;
        lab.style.transform = `translate(${((v.x + 1) / 2) * el.clientWidth}px, ${((1 - v.y) / 2) * el.clientHeight - 18}px) translateX(-50%)`;
      } else if (lab) lab.style.display = "none";
    };
    loop();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      renderer.domElement.removeEventListener("pointermove", onMove);
      controls.dispose();
      mesh.geometry.dispose();
      (mesh.material as THREE.Material).dispose();
      lineGeo.dispose();
      (lines.material as THREE.Material).dispose();
      renderer.dispose();
      renderer.domElement.remove();
      api.current = null;
    };
  }, [data, dark]);

  useEffect(() => {
    live.current = { visibleTypes, locked, lockedEdges, selected, onSelect };
    api.current?.refresh();
  }, [visibleTypes, locked, lockedEdges, selected, onSelect]);

  return (
    <div ref={container} className="relative h-full w-full overflow-hidden" role="img" aria-label={`3D knowledge graph with ${data.nodes.length} nodes and ${data.edges.length} edges. Drag to orbit, scroll to zoom. Use the list view for a text version.`} data-testid="graph-canvas-3d">
      <div ref={label} className="pointer-events-none absolute left-0 top-0 hidden whitespace-nowrap rounded-md border bg-popover/95 px-2 py-0.5 text-xs font-medium shadow" />
      <div ref={hover} className="pointer-events-none absolute z-10 hidden max-w-xs rounded-md border bg-popover/95 px-2 py-1 text-xs shadow" />
    </div>
  );
}
