// globe-shape.ts: the globe's tiles, shared by the 3D globe and the still one. Tiles sit evenly on a sphere
// (a Fibonacci lattice); each belongs to the nearest area centre, so the areas are solid regions like countries.
// Tiles on a border between two areas are marked, so the seams can be drawn smaller and the regions read apart.
// Used by: globe-canvas.tsx, globe-flat.tsx. Uses: areas.ts.
import type { AreaKey } from "@/contracts";
import { AREA_CENTRE, AREA_ORDER } from "./areas";

// Config
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const BORDER_GAP = 0.045; // how close the second-nearest centre must be for a tile to count as a seam

export type Tile = { x: number; y: number; z: number; area: AreaKey; border: boolean };

function unit([x, y, z]: [number, number, number]): [number, number, number] {
  const length = Math.hypot(x, y, z);
  return [x / length, y / length, z / length];
}

export const CENTRES = AREA_ORDER.map((key) => ({ key, at: unit(AREA_CENTRE[key]) }));

// The nearest area wins the tile; the gap to the runner-up says whether it sits on a seam.
function regionOf(x: number, y: number, z: number) {
  const scored = CENTRES.map((c) => ({ key: c.key, closeness: c.at[0] * x + c.at[1] * y + c.at[2] * z })).sort((a, b) => b.closeness - a.closeness);
  return { area: scored[0].key, border: scored[0].closeness - scored[1].closeness < BORDER_GAP };
}

export function makeTiles(count: number): Tile[] {
  return Array.from({ length: count }, (_, i) => {
    const y = 1 - (2 * (i + 0.5)) / count;
    const ring = Math.sqrt(1 - y * y);
    const x = Math.cos(GOLDEN_ANGLE * i) * ring;
    const z = Math.sin(GOLDEN_ANGLE * i) * ring;
    return { x, y, z, ...regionOf(x, y, z) };
  });
}
