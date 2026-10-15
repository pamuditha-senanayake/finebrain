"use client";

import { useEffect, useRef, type MutableRefObject } from "react";

export type VoiceState = "idle" | "listening" | "thinking" | "speaking";

/** How each state moves: edge wobble, swirl speed and how much the live sound level swells the orb. */
const MOTION: Record<VoiceState, { wobble: number; spin: number; swell: number }> = {
  idle: { wobble: 0.012, spin: 0.25, swell: 0 },
  listening: { wobble: 0.03, spin: 0.5, swell: 0.22 },
  thinking: { wobble: 0.025, spin: 2.2, swell: 0 },
  speaking: { wobble: 0.035, spin: 0.7, swell: 0.18 },
};

const BLOBS = [
  { color: "232, 135, 95", r: 0.82, orbit: 0.3, speed: 1, phase: 0 },
  { color: "242, 194, 123", r: 0.7, orbit: 0.36, speed: -0.8, phase: 2.1 },
  { color: "217, 102, 63", r: 0.75, orbit: 0.28, speed: 0.6, phase: 4.2 },
  { color: "250, 225, 190", r: 0.45, orbit: 0.42, speed: -1.3, phase: 1 },
];

/**
 * A large glowing orb for the voice agent, drawn on a canvas. It breathes when idle, swells with your voice while
 * listening, swirls while thinking and pulses while speaking. `level` (0 to 1) is read every frame, so updating it
 * never re-renders React.
 */
export function VoiceOrb({ state, level, size = 280 }: { state: VoiceState; level: MutableRefObject<number>; size?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    const cv = canvas.current;
    if (!cv) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const W = size * 1.6;
    cv.width = W * dpr;
    cv.height = W * dpr;
    ctx.scale(dpr, dpr);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let smooth = 0;
    let spin = 0;
    let last = performance.now();
    const c = W / 2;
    const base = size * 0.4;

    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = reduce ? 0 : now / 1000;
      const m = MOTION[stateRef.current];
      smooth += (clamp(level.current) - smooth) * 0.18;
      spin += dt * m.spin * (reduce ? 0 : 1);
      const breath = reduce ? 0 : Math.sin(t * 1.3) * 0.02;
      const R = base * (1 + breath + smooth * m.swell);

      ctx.clearRect(0, 0, W, W);
      // Glow around the orb, stronger with sound.
      const glow = ctx.createRadialGradient(c, c, R * 0.6, c, c, R * 1.75);
      glow.addColorStop(0, `rgba(232, 135, 95, ${0.32 + smooth * 0.3})`);
      glow.addColorStop(1, "rgba(232, 135, 95, 0)");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, W, W);

      // The orb's edge wobbles a little, more when there is sound.
      ctx.save();
      ctx.beginPath();
      const steps = 96;
      for (let i = 0; i <= steps; i++) {
        const a = (i / steps) * Math.PI * 2;
        const w = m.wobble + smooth * 0.05;
        const r = R * (1 + w * Math.sin(a * 3 + t * 1.7) + w * 0.6 * Math.sin(a * 5 - t * 2.3));
        const x = c + Math.cos(a) * r;
        const y = c + Math.sin(a) * r;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.clip();
      const bg = ctx.createRadialGradient(c - R * 0.3, c - R * 0.35, R * 0.1, c, c, R * 1.1);
      bg.addColorStop(0, "#f6b48f");
      bg.addColorStop(0.55, "#e0754b");
      bg.addColorStop(1, "#a9472a");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, W);
      // Soft coloured blobs swirl inside.
      for (const b of BLOBS) {
        const a = spin * b.speed + b.phase;
        const x = c + Math.cos(a) * R * b.orbit;
        const y = c + Math.sin(a * 1.1) * R * b.orbit;
        const r = R * b.r * (1 + smooth * 0.15);
        const g = ctx.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, `rgba(${b.color}, 0.75)`);
        g.addColorStop(1, `rgba(${b.color}, 0)`);
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, W, W);
      }
      // A highlight, as if lit from the top left.
      const shine = ctx.createRadialGradient(c - R * 0.38, c - R * 0.42, 0, c - R * 0.38, c - R * 0.42, R * 0.55);
      shine.addColorStop(0, "rgba(255, 255, 255, 0.55)");
      shine.addColorStop(1, "rgba(255, 255, 255, 0)");
      ctx.fillStyle = shine;
      ctx.fillRect(0, 0, W, W);
      ctx.restore();

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size, level]);

  return <canvas ref={canvas} style={{ width: size * 1.6, height: size * 1.6 }} className="pointer-events-none select-none" role="img" aria-label={`Voice agent, ${state}`} />;
}

function clamp(v: number) {
  return Math.max(0, Math.min(1, Number.isFinite(v) ? v : 0));
}
