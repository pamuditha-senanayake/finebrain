/** mulberry32: small, fast, deterministic. The same seed always yields the same sequence. */
export function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export class Rng {
  private next: () => number;
  constructor(seed: number | string) {
    this.next = mulberry32(typeof seed === "string" ? hashString(seed) : seed);
  }
  float() {
    return this.next();
  }
  int(min: number, max: number) {
    return Math.floor(this.next() * (max - min + 1)) + min;
  }
  pick<T>(items: readonly T[]): T {
    return items[Math.floor(this.next() * items.length)];
  }
  chance(p: number) {
    return this.next() < p;
  }
  weighted<T>(items: readonly [T, number][]): T {
    const total = items.reduce((s, [, w]) => s + w, 0);
    let r = this.next() * total;
    for (const [item, w] of items) {
      r -= w;
      if (r <= 0) return item;
    }
    return items[items.length - 1][0];
  }
  sample<T>(items: readonly T[], n: number): T[] {
    const copy = [...items];
    const out: T[] = [];
    while (out.length < n && copy.length) out.push(copy.splice(Math.floor(this.next() * copy.length), 1)[0]);
    return out;
  }
}

/** Fixed anchor so seed output never depends on the wall clock: 8 Oct 2026, 09:00 Asia/Colombo. */
export const SEED_NOW = Date.parse("2026-10-08T03:30:00.000Z");
export const HOUR = 3_600_000;
export const DAY = 86_400_000;
export const iso = (ms: number) => new Date(ms).toISOString();
