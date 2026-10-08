"use client";

import { animate, useInView, useReducedMotion } from "motion/react";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import type { Criticality } from "@/contracts";
import { cn } from "@/lib/utils";

/** Thinking orb: an agent is working, and what kind of work. Idle agents get a static dot. */
export function ThinkingOrb({ kind, size = 14, className }: { kind: "retrieval" | "judgment" | "tool" | null | undefined; size?: number; className?: string }) {
  if (!kind) return <IdleDot className={className} />;
  return <span className={cn("orb inline-block shrink-0", className)} data-kind={kind} style={{ width: size, height: size }} role="img" aria-label={`working: ${kind}`} />;
}

export function IdleDot({ className, tone = "neutral" }: { className?: string; tone?: "neutral" | "risk" | "warn" }) {
  return <span className={cn("inline-block size-2 shrink-0 rounded-full", tone === "risk" ? "bg-risk" : tone === "warn" ? "bg-warn" : "bg-muted-foreground/50", className)} aria-hidden />;
}

/** Border beam budget: at most three live highlights per screen. */
const BeamBudget = createContext<{ claim: () => boolean } | null>(null);
export function BeamScope({ children, max = 3 }: { children: ReactNode; max?: number }) {
  const used = useRef(0);
  return <BeamBudget.Provider value={{ claim: () => (used.current < max ? (used.current += 1, true) : false) }}>{children}</BeamBudget.Provider>;
}

/** Border beam: live and needs attention now. */
export function Beam({ active = true, children, className, color }: { active?: boolean; children: ReactNode; className?: string; color?: string }) {
  const budget = useContext(BeamBudget);
  const [granted] = useState(() => (active ? (budget ? budget.claim() : true) : false));
  return (
    <div className={cn(active && granted && "beam", className)} style={color ? ({ "--beam-color": color } as React.CSSProperties) : undefined}>
      {children}
    </div>
  );
}

/** Liquid metal: irreversible commitment. Only C3 and C4 commits get the metal finish. */
export function CommitButton({ criticality, children, className, ...props }: React.ComponentProps<typeof Button> & { criticality: Criticality }) {
  const metal = criticality >= 3;
  return (
    <Button {...props} className={cn(metal && "metal hover:brightness-105", className)} variant={metal ? "outline" : props.variant ?? "default"}>
      {children}
    </Button>
  );
}

/** Ambient surface: the brain's presence. Progressive enhancement, complete without it. */
export function AmbientSurface({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("ambient relative overflow-hidden", className)}>{children}</div>;
}

/** Number change tween for KPIs. Respects reduced motion. */
export function NumberTween({ value, format = (n) => n.toFixed(0) }: { value: number; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const prev = useRef(0);
  useEffect(() => {
    if (!ref.current) return;
    if (reduce || !inView) {
      ref.current.textContent = format(value);
      prev.current = value;
      return;
    }
    const controls = animate(prev.current, value, {
      duration: 0.6,
      ease: "easeOut",
      onUpdate: (v) => {
        if (ref.current) ref.current.textContent = format(v);
      },
    });
    prev.current = value;
    return () => controls.stop();
  }, [value, inView, reduce, format]);
  return <span ref={ref} className="tabular">{format(value)}</span>;
}
