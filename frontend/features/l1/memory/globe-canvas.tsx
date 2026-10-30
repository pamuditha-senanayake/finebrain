"use client";

// globe-canvas.tsx: the living memory as one globe. Eight areas are solid regions of tightly packed tiles, like
// countries, with thin seams between them; an opaque core hides the far side so no colours mix. It turns slowly
// while idle, stops under the cursor, ripples where the cursor touches, turns a chosen area to the front, and lifts it.
// Every area carries a callout: a circle on its region (or on the rim when it is behind), a straight line out, one
// rounded corner, then the label with its traces and drift. The wheel or the + and − buttons zoom.
// Used by: memory.tsx. Uses: areas.ts, globe-shape.ts, three.
import { Minus, Plus } from "lucide-react";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { AreaKey, MemoryArea } from "@/contracts";
import { cn } from "@/lib/utils";
import { AREA_COLOR, cssColor, driftTotal } from "./areas";
import { CENTRES, makeTiles } from "./globe-shape";

// Config
const TILE_COUNT = 9000;
const TILE_SIZE = 0.03; // world units: tiles nearly touch, so an area reads as one region
const SEAM_SIZE = 0.4; // share of a tile's size on a border between two areas
const RIPPLE_ANGLE = 0.34; // radians around the cursor that ripple
const RIPPLE_LIFT = 0.06;
const FOCUS_LIFT = 0.03; // the hovered or chosen area rises off the globe
const SPIN = 0.07; // radians a second while idle
const EASE = 0.12; // share of the gap closed each frame, for lifts and turns
// Globe radius as a share of the box's shorter side, leaving room for labels. A tall, narrow box (a card is open,
// or a phone) has room above and below, so the globe can take more of its width.
const GLOBE_SHARE = { wide: 0.31, narrow: 0.4 };
const LABELS_MIN_WIDTH = 520;
const LABEL_GAP = 40;
const EDGE = 12; // px a label keeps from the box's edge
const TITLE_CLEARANCE = 150; // px from the top the page title takes, on the left
const ZOOM_MIN = 0.6;
const ZOOM_MAX = 2.2;
const ZOOM_STEP = 1.25;
const FRONT = new THREE.Vector3(0, 0.18, 1).normalize();
// Halo strength per theme; the colours themselves come from globals.css (--globe-core, --globe-glow, --area-*).
const GLOW_STRENGTH = { dark: 0.32, light: 0.28 };

type Props = { areas: MemoryArea[]; selected: AreaKey | null; onSelect: (key: AreaKey) => void; theme: string };

const TILE_VERTEX = `attribute float size; attribute float lift; attribute vec3 tint; uniform float scale; varying vec3 vTint; varying float vFacing;
void main() {
  vec4 mv = modelViewMatrix * vec4(position * (1.0 + lift), 1.0);
  vTint = tint;
  vFacing = normalize(normalMatrix * position).z;
  gl_PointSize = size * scale / -mv.z;
  gl_Position = projectionMatrix * mv;
}`;
// Colours arrive in linear space (three converts the CSS hex); colorspace_fragment turns them back into sRGB, so a
// tile shows the exact colour of its legend dot.
const TILE_FRAGMENT = `varying vec3 vTint; varying float vFacing;
void main() {
  if (length(gl_PointCoord - 0.5) > 0.5) discard;
  gl_FragColor = vec4(vTint * (0.82 + 0.18 * vFacing), 1.0);
  #include <colorspace_fragment>
}`;
// A soft halo around the rim, brighter at the edge, so the globe stands off the page in both themes.
const GLOW_VERTEX = `varying float vEdge; void main() { vEdge = 1.0 - abs(normalize(normalMatrix * normal).z); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const GLOW_FRAGMENT = `uniform vec3 glow; uniform float strength; varying float vEdge;
void main() {
  gl_FragColor = vec4(glow, pow(vEdge, 5.0) * strength);
  #include <colorspace_fragment>
}`;

// --- Colour and lift

// The chosen or hovered area is bright and lifted; other areas turn a calm grey while one is chosen; quiet areas fade.
function paint(tint: Float32Array, size: Float32Array, tiles: ReturnType<typeof makeTiles>, areas: Map<AreaKey, MemoryArea>, focus: AreaKey | null, fadeTo: string) {
  const palette = Object.fromEntries(CENTRES.map(({ key }) => [key, cssColor(`--area-${key}`)])) as Record<AreaKey, string>;
  const colour = new THREE.Color();
  const base = new THREE.Color(fadeTo);
  tiles.forEach((tile, i) => {
    const quiet = (areas.get(tile.area)?.traces7d ?? 0) === 0;
    const fade = focus ? (tile.area === focus ? 0 : 0.7) : quiet ? 0.6 : 0;
    colour.set(palette[tile.area]).lerp(base, fade);
    tint.set([colour.r, colour.g, colour.b], i * 3);
    size[i] = TILE_SIZE * (tile.border ? SEAM_SIZE : 1);
  });
}

// Where the cursor's ray meets the globe, in the globe's own turning frame, or null if it misses.
function hitOnGlobe(ray: THREE.Ray, globe: THREE.Object3D) {
  const local = ray.clone().applyMatrix4(globe.matrixWorld.clone().invert());
  const hit = local.intersectSphere(new THREE.Sphere(new THREE.Vector3(), 1), new THREE.Vector3());
  return hit ? hit.normalize() : null;
}

function nearestArea(p: THREE.Vector3): AreaKey {
  return CENTRES.reduce((best, c) => (c.at[0] * p.x + c.at[1] * p.y + c.at[2] * p.z > best.score ? { key: c.key, score: c.at[0] * p.x + c.at[1] * p.y + c.at[2] * p.z } : best), { key: CENTRES[0].key, score: -2 }).key;
}

// --- Callouts

// From the region straight out, one rounded corner, then level to the label's edge.
function calloutPath(ax: number, ay: number, bx: number, by: number, ex: number) {
  const sx = Math.sign(ex - bx) || 1;
  const r = Math.min(10, Math.abs(ex - bx) / 2);
  const back = Math.hypot(bx - ax, by - ay) || 1;
  const cx = bx - ((bx - ax) / back) * r;
  const cy = by - ((by - ay) / back) * r;
  return `M${ax},${ay} L${cx},${cy} Q${bx},${by} ${bx + sx * r},${by} H${ex}`;
}

// Labels on one side sit in the order of their callouts and never closer than LABEL_GAP, inside the box.
function spreadRows(items: { key: AreaKey; by: number }[], height: number, top: number) {
  const sorted = [...items].sort((a, b) => a.by - b.by);
  let last = -Infinity;
  const rows = sorted.map((item) => (last = Math.max(item.by, last + LABEL_GAP, top)));
  const overflow = Math.max(0, (rows[rows.length - 1] ?? 0) - (height - LABEL_GAP / 2));
  return new Map(sorted.map((item, i) => [item.key, rows[i] - overflow]));
}

export default function GlobeCanvas({ areas, selected, onSelect, theme }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const labels = useRef(new Map<AreaKey, HTMLButtonElement>());
  const lines = useRef(new Map<AreaKey, SVGGElement>());
  const live = useRef({ areas, selected, onSelect, theme, hovered: null as AreaKey | null, repaint: () => {}, retheme: () => {}, zoomBy: (factor: number) => void factor });

  useEffect(() => {
    Object.assign(live.current, { areas, selected, onSelect, theme });
    live.current.retheme();
    live.current.repaint();
  }, [areas, selected, onSelect, theme]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    // Step 1: renderer, camera, the core, the halo and the tiles
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    const canvas = renderer.domElement;
    Object.assign(canvas.style, { position: "absolute", inset: "0", cursor: "grab" });
    el.prepend(canvas);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 50);
    const globe = new THREE.Group();
    scene.add(globe);
    const core = new THREE.Mesh(new THREE.SphereGeometry(0.985, 64, 48), new THREE.MeshBasicMaterial());
    globe.add(core);
    const glowMaterial = new THREE.ShaderMaterial({ vertexShader: GLOW_VERTEX, fragmentShader: GLOW_FRAGMENT, side: THREE.BackSide, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { glow: { value: new THREE.Color() }, strength: { value: 0 } } });
    scene.add(new THREE.Mesh(new THREE.SphereGeometry(1.07, 48, 32), glowMaterial));
    const tiles = makeTiles(TILE_COUNT);
    const tint = new Float32Array(TILE_COUNT * 3);
    const size = new Float32Array(TILE_COUNT);
    const lift = new Float32Array(TILE_COUNT);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(tiles.flatMap((t) => [t.x, t.y, t.z])), 3));
    geometry.setAttribute("tint", new THREE.BufferAttribute(tint, 3));
    geometry.setAttribute("size", new THREE.BufferAttribute(size, 1));
    geometry.setAttribute("lift", new THREE.BufferAttribute(lift, 1));
    const tileMaterial = new THREE.ShaderMaterial({ vertexShader: TILE_VERTEX, fragmentShader: TILE_FRAGMENT, uniforms: { scale: { value: 1 } } });
    globe.add(new THREE.Points(geometry, tileMaterial));

    // Step 2: colours follow the data, the theme and the focus
    // The theme's class is on <html> already, so the CSS variables hold this theme's colours
    live.current.retheme = () => {
      (core.material as THREE.MeshBasicMaterial).color.set(cssColor("--globe-core"));
      glowMaterial.uniforms.glow.value.set(cssColor("--globe-glow"));
      glowMaterial.uniforms.strength.value = GLOW_STRENGTH[live.current.theme === "light" ? "light" : "dark"];
    };
    live.current.repaint = () => {
      paint(tint, size, tiles, new Map(live.current.areas.map((a) => [a.key, a])), live.current.hovered ?? live.current.selected, cssColor("--globe-fade"));
      geometry.attributes.tint.needsUpdate = true;
      geometry.attributes.size.needsUpdate = true;
    };
    live.current.retheme();
    live.current.repaint();

    // Step 3: the cursor ripples and points at an area; a drag turns the globe; a click opens the area
    const pointer = { inside: false, ndc: new THREE.Vector2(), hit: null as THREE.Vector3 | null, down: null as { x: number; y: number } | null, moved: 0 };
    const raycaster = new THREE.Raycaster();
    const onMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer.ndc.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
      if (pointer.down) {
        const turn = new THREE.Quaternion().setFromEuler(new THREE.Euler(e.movementY * 0.005, e.movementX * 0.005, 0));
        globe.quaternion.premultiply(turn);
        pointer.moved += Math.abs(e.movementX) + Math.abs(e.movementY);
      }
    };
    const onDown = (e: PointerEvent) => {
      Object.assign(pointer, { down: { x: e.clientX, y: e.clientY }, moved: 0 });
      canvas.style.cursor = "grabbing";
    };
    const onUp = () => {
      const clicked = pointer.down && pointer.moved < 5;
      pointer.down = null;
      canvas.style.cursor = live.current.hovered ? "pointer" : "grab";
      if (clicked && live.current.hovered) live.current.onSelect(live.current.hovered);
    };
    const onEnter = () => (pointer.inside = true);
    const onLeave = () => Object.assign(pointer, { inside: false, hit: null, down: null });
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerdown", onDown);
    window.addEventListener("pointerup", onUp);
    el.addEventListener("pointerenter", onEnter);
    el.addEventListener("pointerleave", onLeave);

    // Step 4: fit to the box; a narrow box pulls the camera back so the whole globe shows
    const fit = () => {
      const { width, height } = el.getBoundingClientRect();
      // A box not laid out yet has no size; fitting to it would put the camera at infinity
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      Object.assign(canvas.style, { width: `${width}px`, height: `${height}px` });
      camera.aspect = width / Math.max(1, height);
      // The globe's radius is a fixed share of the box's shorter side, whatever its shape
      const focal = height / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)));
      view.distance = focal / (GLOBE_SHARE[width < height ? "narrow" : "wide"] * Math.min(width, height));
      camera.updateProjectionMatrix();
      tileMaterial.uniforms.scale.value = renderer.getPixelRatio() * focal;
      place();
    };
    // Zoom moves the camera, never the globe, so tiles keep their spacing; callouts project before the first render,
    // so the view matrix is made current here rather than at render time
    const view = { distance: 0, zoom: 1 };
    const place = () => {
      camera.position.set(0, 0, view.distance / view.zoom);
      camera.updateMatrixWorld();
    };
    live.current.zoomBy = (factor: number) => {
      view.zoom = THREE.MathUtils.clamp(view.zoom * factor, ZOOM_MIN, ZOOM_MAX);
      place();
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      live.current.zoomBy(Math.exp(-e.deltaY * 0.0015));
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    const resize = new ResizeObserver(fit);
    resize.observe(el);
    fit();

    // Step 5: every frame, turn, find the hovered area, lift and ripple the tiles, then move the callouts
    const clock = new THREE.Clock();
    const v = new THREE.Vector3();
    let frame = 0;
    const turn = (dt: number) => {
      const chosen = CENTRES.find((c) => c.key === live.current.selected);
      if (chosen) {
        v.set(...chosen.at).applyQuaternion(globe.quaternion);
        const target = new THREE.Quaternion().setFromUnitVectors(v, FRONT).multiply(globe.quaternion);
        globe.quaternion.slerp(target, EASE * 0.6);
      } else if (!pointer.inside && !pointer.down) {
        globe.quaternion.premultiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), SPIN * dt));
      }
      globe.updateMatrixWorld();
    };
    const hover = () => {
      raycaster.setFromCamera(pointer.ndc, camera);
      pointer.hit = pointer.inside ? hitOnGlobe(raycaster.ray, globe) : null;
      const hovered = pointer.hit && !pointer.down ? nearestArea(pointer.hit) : null;
      if (hovered === live.current.hovered) return;
      live.current.hovered = hovered;
      canvas.style.cursor = pointer.down ? "grabbing" : hovered ? "pointer" : "grab";
      live.current.repaint();
    };
    const raise = (t: number) => {
      const focus = live.current.hovered ?? live.current.selected;
      const hit = pointer.hit;
      for (let i = 0; i < TILE_COUNT; i++) {
        const tile = tiles[i];
        let target = tile.area === focus ? FOCUS_LIFT : 0;
        if (hit) {
          const angle = Math.acos(Math.min(1, tile.x * hit.x + tile.y * hit.y + tile.z * hit.z));
          if (angle < RIPPLE_ANGLE) target += (1 - angle / RIPPLE_ANGLE) ** 2 * RIPPLE_LIFT * (0.6 + 0.4 * Math.sin(angle * 32 - t * 6));
        }
        lift[i] += (target - lift[i]) * EASE;
      }
      geometry.attributes.lift.needsUpdate = true;
    };
    // Every area keeps its label. One facing you starts its callout on its region; one behind the globe starts on the
    // rim, on the side it sits, with a dashed line and a softer label, so you always see where the work and the drift are.
    const moveCallouts = (width: number, height: number) => {
      // Until the first fit the camera sits inside the globe and every projection is NaN
      if (!width || !height || camera.position.z === 0) return;
      const toCamera = camera.position.clone().normalize();
      const centre = new THREE.Vector3().project(camera);
      const cx = (centre.x + 1) * 0.5 * width;
      const cy = (1 - centre.y) * 0.5 * height;
      const rim = (new THREE.Vector3(1, 0, 0).project(camera).x - centre.x) * 0.5 * width;
      const shown = width >= LABELS_MIN_WIDTH; // on a phone the legend below the globe carries names and counts
      const items = CENTRES.map((c, i) => {
        v.set(...c.at).applyQuaternion(globe.quaternion);
        const front = v.dot(toCamera) > 0.05;
        let ax: number;
        let ay: number;
        if (front) {
          v.multiplyScalar(1.01).project(camera);
          [ax, ay] = [(v.x + 1) * 0.5 * width, (1 - v.y) * 0.5 * height];
        } else {
          const side = Math.hypot(v.x, v.y) > 0.05 ? Math.atan2(-v.y, v.x) : (i / CENTRES.length) * Math.PI * 2;
          [ax, ay] = [cx + Math.cos(side) * rim, cy + Math.sin(side) * rim];
        }
        const out = Math.hypot(ax - cx, ay - cy) || 1;
        const bx = ax + ((ax - cx) / out) * 46;
        return { key: c.key, front, ax, ay, bx, by: ay + ((ay - cy) / out) * 46, right: bx >= cx };
      });
      // The page title sits top left, so labels on the left start below it
      const rows = new Map([...spreadRows(items.filter((i) => !i.right), height, TITLE_CLEARANCE), ...spreadRows(items.filter((i) => i.right), height, LABEL_GAP / 2)]);
      for (const item of items) {
        const label = labels.current.get(item.key);
        const line = lines.current.get(item.key);
        if (!label || !line) continue;
        label.style.opacity = shown ? (item.front ? "1" : "0.62") : "0";
        line.style.opacity = shown ? (item.front ? "0.9" : "0.45") : "0";
        label.style.pointerEvents = shown ? "auto" : "none";
        if (!shown) continue;
        const y = rows.get(item.key)!;
        // Labels stay inside the box: one that would cross its edge slides in, and its line ends where it starts
        const wanted = item.bx + (item.right ? 22 : -22);
        const x = item.right ? Math.min(wanted, width - EDGE - label.offsetWidth) : Math.max(EDGE, wanted - label.offsetWidth);
        const ex = item.right ? x : x + label.offsetWidth;
        label.style.transform = `translate(${x}px, ${y - label.offsetHeight / 2}px)`;
        const path = line.querySelector("path")!;
        path.setAttribute("d", calloutPath(item.ax, item.ay, item.bx, y, ex));
        path.setAttribute("stroke-dasharray", item.front ? "" : "3 4");
        line.querySelector("circle")!.setAttribute("cx", String(item.ax));
        line.querySelector("circle")!.setAttribute("cy", String(item.ay));
      }
    };
    const loop = () => {
      const dt = Math.min(0.05, clock.getDelta());
      turn(dt);
      hover();
      raise(clock.elapsedTime);
      moveCallouts(el.clientWidth, el.clientHeight);
      renderer.render(scene, camera);
      frame = requestAnimationFrame(loop);
    };
    loop();

    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointerenter", onEnter);
      el.removeEventListener("pointerleave", onLeave);
      geometry.dispose();
      tileMaterial.dispose();
      glowMaterial.dispose();
      renderer.dispose();
      canvas.remove();
    };
  }, []);

  // Labels are for the pointer; the legend beside the globe is the keyboard and screen reader way in. Zoom is for both.
  return (
    <div ref={box} className="absolute inset-0 touch-none">
      <svg className="pointer-events-none absolute inset-0 size-full overflow-visible" aria-hidden>
        {CENTRES.map(({ key }) => (
          <g key={key} ref={(g) => void (g && lines.current.set(key, g))} stroke={AREA_COLOR[key]} fill="none" style={{ opacity: 0 }}>
            <path strokeWidth={selected === key ? 2 : 1.4} />
            <circle r={4.5} fill="var(--background)" strokeWidth={2} />
          </g>
        ))}
      </svg>
      <div aria-hidden>
        {CENTRES.map(({ key }) => {
          const area = areas.find((a) => a.key === key);
          if (!area) return null;
          const drift = driftTotal(area);
          return (
            <button key={key} ref={(b) => void (b && labels.current.set(key, b))} type="button" tabIndex={-1} onClick={() => onSelect(key)} style={{ opacity: 0 }}
              className={cn("absolute left-0 top-0 flex items-center gap-2 whitespace-nowrap rounded-full border bg-card/90 px-3 py-1.5 text-[14px] shadow-sm backdrop-blur transition-opacity hover:bg-card hover:!opacity-100", selected === key && "border-foreground/40")}>
              <span className="size-2.5 rounded-full" style={{ background: AREA_COLOR[key] }} />
              <span className="font-medium">{area.name}</span>
              <span className="tabular-nums text-muted-foreground">{area.traces7d} traces</span>
              {drift > 0 && <span className="rounded-full bg-primary px-2 text-[12px] font-semibold text-primary-foreground tabular-nums">{drift} drifting</span>}
            </button>
          );
        })}
      </div>
      <div className="absolute bottom-5 right-5 flex flex-col overflow-hidden rounded-xl border bg-card/85 shadow-sm backdrop-blur">
        <button type="button" onClick={() => live.current.zoomBy(ZOOM_STEP)} aria-label="Zoom in" className="flex size-9 items-center justify-center hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"><Plus className="size-4" aria-hidden /></button>
        <button type="button" onClick={() => live.current.zoomBy(1 / ZOOM_STEP)} aria-label="Zoom out" className="flex size-9 items-center justify-center border-t hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"><Minus className="size-4" aria-hidden /></button>
      </div>
    </div>
  );
}
