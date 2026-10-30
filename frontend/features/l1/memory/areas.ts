// areas.ts: each brain area's colour (from globals.css) and its place on the globe, shared by the 3D globe, the still globe, the legend
// and the cards. Used by: globe-canvas.tsx, globe-flat.tsx, globe-shape.ts, memory.tsx, area-card.tsx, traces.tsx,
// features/l2/skills-from-traces.tsx. Uses: contracts (AreaKey).
import { AreaKey, type MemoryArea } from "@/contracts";

// Config
// Each area's colour lives in app/globals.css (--area-*), one value per theme, so the page and the globe agree.
export const AREA_COLOR = Object.fromEntries(AreaKey.options.map((key) => [key, `var(--area-${key})`])) as Record<AreaKey, string>;

/** The colour a CSS variable holds right now, for three.js, which cannot read var(). */
export function cssColor(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// The centre of each area on the globe, as a direction (x right, y up, z towards you). Spread so every area gets a
// region of about the same size; the busiest areas sit on the front of the globe when it first loads.
export const AREA_CENTRE: Record<AreaKey, [number, number, number]> = {
  customer_care: [-0.42, 0.28, 0.86], operations: [0.5, 0.32, 0.8], finance: [0.05, -0.62, 0.78],
  sales: [-0.95, -0.25, -0.15], legal: [0.92, -0.3, -0.2], product: [0.0, 0.95, -0.3],
  people: [-0.35, -0.2, -0.92], general: [0.45, -0.75, -0.48],
};

// Legend and keyboard order: busiest areas first.
export const AREA_ORDER: AreaKey[] = ["customer_care", "operations", "finance", "sales", "legal", "product", "people", "general"];

export function driftTotal(area: MemoryArea) {
  return area.drift.skill + area.drift.policy + area.drift.security;
}

export function areaLabel(area: MemoryArea) {
  const drift = driftTotal(area);
  return `${area.name}: ${area.traces7d} traces this week${drift ? `, ${drift} drifting` : ""}`;
}
