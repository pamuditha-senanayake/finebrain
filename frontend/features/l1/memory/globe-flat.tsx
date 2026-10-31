// globe-flat.tsx: the still globe, for reduced motion or a browser without WebGL. The front half of the same tiles,
// drawn flat, with the same regions and colours as the 3D globe and nothing moving. A click on a region opens it.
// Used by: memory.tsx. Uses: areas.ts, globe-shape.ts.
import type { MouseEvent } from "react";
import type { AreaKey, MemoryArea } from "@/contracts";
import { AREA_COLOR } from "./areas";
import { makeTiles } from "./globe-shape";

// Config
const TILE_COUNT = 5000;
const SIZE = 600;
const FRONT_TILES = makeTiles(TILE_COUNT).filter((t) => t.z > 0);

export default function GlobeFlat({ areas, selected, onSelect }: { areas: MemoryArea[]; selected: AreaKey | null; onSelect: (key: AreaKey) => void }) {
  const byKey = new Map(areas.map((a) => [a.key, a]));
  // One handler for every tile: the tile carries its area.
  const pick = (e: MouseEvent<SVGSVGElement>) => {
    const area = (e.target as SVGElement).dataset.area as AreaKey | undefined;
    if (area) onSelect(area);
  };
  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="absolute inset-0 m-auto size-full max-h-[80%] max-w-[80%]" onClick={pick} aria-hidden>
      <circle cx={SIZE / 2} cy={SIZE / 2} r={SIZE / 2 - 4} className="fill-muted" />
      {FRONT_TILES.map((tile, i) => {
        const quiet = (byKey.get(tile.area)?.traces7d ?? 0) === 0;
        const opacity = selected ? (tile.area === selected ? 1 : 0.35) : quiet ? 0.45 : 1;
        return <circle key={i} data-area={tile.area} cx={SIZE / 2 + tile.x * (SIZE / 2 - 8)} cy={SIZE / 2 - tile.y * (SIZE / 2 - 8)} r={tile.border ? 1.6 : 3.6} fill={AREA_COLOR[tile.area]} opacity={opacity} className="cursor-pointer" />;
      })}
    </svg>
  );
}
