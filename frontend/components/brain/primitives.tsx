"use client";

import { AlertTriangle, Inbox, Lock, RefreshCw } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import type { Criticality, Env } from "@/contracts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CRITICALITY_LABEL } from "@/lib/governance/criticality";
import { t } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const CRIT_CLASS: Record<Criticality, string> = {
  0: "text-crit-0 bg-crit-0/10 ring-crit-0/30",
  1: "text-crit-1 bg-crit-1/10 ring-crit-1/30",
  2: "text-crit-2 bg-crit-2/12 ring-crit-2/35",
  3: "text-crit-3 bg-crit-3/12 ring-crit-3/35",
  4: "text-crit-4 bg-crit-4/12 ring-crit-4/40",
};

export function CritBadge({ level, showLabel = false, className }: { level: Criticality | number; showLabel?: boolean; className?: string }) {
  const l = Math.max(0, Math.min(4, level)) as Criticality;
  return (
    <span className={cn("inline-flex h-5 items-center gap-1 rounded-md px-1.5 text-[11px] font-semibold ring-1 ring-inset tabular", CRIT_CLASS[l], className)} title={`C${l} ${CRITICALITY_LABEL[l]}`}>
      C{l}
      {showLabel && <span className="font-medium">{CRITICALITY_LABEL[l]}</span>}
    </span>
  );
}

export function EnvBadge({ env, branch }: { env: Env; branch?: string }) {
  const cls = env === "production" ? "bg-env-production text-white" : env === "staging" ? "bg-env-staging text-black" : "bg-env-sandbox text-white";
  return <span className={cn("inline-flex h-5 items-center rounded px-1.5 text-[10px] font-bold uppercase tracking-wide", cls)}>{env === "sandbox" && branch ? branch.replace("sandbox/", "sbx/") : env}</span>;
}

export type Tone = "ok" | "warn" | "risk" | "neutral" | "info" | "agent";
const TONE: Record<Tone, string> = {
  ok: "bg-ok/12 text-ok ring-ok/30",
  warn: "bg-warn/15 text-warn-fg ring-warn/35",
  risk: "bg-risk/12 text-risk ring-risk/30",
  neutral: "bg-muted text-muted-foreground ring-border",
  info: "bg-secondary text-secondary-foreground ring-foreground/12",
  agent: "bg-agent/12 text-agent ring-agent/30",
};

export function StatusChip({ tone, children, className }: { tone: Tone; children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-full px-2 text-[11px] font-medium ring-1 ring-inset", TONE[tone], className)}>{children}</span>;
}

export function statusTone(status: string): Tone {
  if (["succeeded", "approved", "merged", "green", "ok", "active", "complete", "verified", "kept", "fulfilled", "allow", "done", "resolved", "positive"].includes(status)) return "ok";
  if (["escalated", "awaiting_approval", "pending", "amber", "degraded", "partial", "stale", "testing", "open", "proposed", "previewed", "awaiting_grant_approval", "changes_requested", "draft", "unverified"].includes(status)) return "warn";
  if (["failed", "blocked", "rejected", "red", "down", "error", "deny", "expired", "conflict", "conflicted", "negative", "revoked"].includes(status)) return "risk";
  if (["running", "working", "human"].includes(status)) return "agent";
  return "neutral";
}

export function Status({ value }: { value: string }) {
  return <StatusChip tone={statusTone(value)}>{value.replaceAll("_", " ")}</StatusChip>;
}

export function SampleBadge() {
  return (
    <Badge variant="outline" className="border-warn/50 text-[10px] uppercase tracking-wide text-warn-fg">
      Sample
    </Badge>
  );
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-mono text-[12px]", className)}>{children}</span>;
}

export function PageHeader({ title, description, actions, eyebrow }: { title: string; description?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:mb-10 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="mb-2 text-xs font-medium text-muted-foreground">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px] sm:leading-tight">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-[14.5px] leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** A titled block. `plain` sits on the page with no box, for tables and lists that already carry their own frame. */
export function Section({ title, description, actions, children, className, plain = false }: { title?: ReactNode; description?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; plain?: boolean }) {
  return (
    <section className={cn(plain ? "" : "rounded-2xl border bg-card p-5 shadow-xs sm:p-6", className)}>
      {(title || actions) && (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="text-[15px] font-semibold tracking-tight">{title}</h2>}
            {description && <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Kpi({ label, value, hint, tone, className }: { label: string; value: ReactNode; hint?: ReactNode; tone?: Tone; className?: string }) {
  return (
    <div className={cn("rounded-2xl border bg-card px-5 py-4 shadow-xs", className)}>
      <div className="text-[11px] font-medium uppercase tracking-[0.07em] text-muted-foreground">{label}</div>
      <div className={cn("mt-2 text-2xl font-semibold tracking-tight tabular", tone === "risk" && "text-risk", tone === "ok" && "text-ok", tone === "warn" && "text-warn-fg")}>{value}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

export function LoadingState({ rows = 6, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="space-y-2" role="status" aria-live="polite" aria-label={label}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" style={{ opacity: 1 - i * 0.1 }} />
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  );
}

export function EmptyState({ title = t("state.empty"), description, action }: { title?: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="ambient relative overflow-hidden rounded-xl border border-dashed p-8 text-center">
      <div className="relative">
        <Inbox className="mx-auto mb-2 size-6 text-muted-foreground" aria-hidden />
        <p className="text-sm font-medium">{title}</p>
        {description && <p className="mt-1 text-xs text-muted-foreground">{description}</p>}
        {action && <div className="mt-3">{action}</div>}
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-risk/40 bg-risk/5 p-5">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 text-risk" aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-medium">{t("state.error")}</p>
          <p className="mt-1 break-words text-xs text-muted-foreground">{error instanceof Error ? error.message : String(error)}</p>
          {onRetry && (
            <Button size="sm" variant="outline" className="mt-3" onClick={onRetry}>
              <RefreshCw /> {t("state.retry")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export function DeniedState({ reason, home }: { reason?: string; home?: string }) {
  return (
    <div role="alert" className="mx-auto mt-10 max-w-md rounded-xl border bg-card p-6 text-center">
      <Lock className="mx-auto mb-2 size-6 text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium">{t("state.denied")}</p>
      {reason && <p className="mt-1 text-xs text-muted-foreground">{reason}</p>}
      {home && (
        <Button asChild size="sm" variant="outline" className="mt-4">
          <Link href={home}>Go to your home</Link>
        </Button>
      )}
    </div>
  );
}

type QueryLike<T> = { data: T | undefined; isLoading: boolean; error: unknown; refetch: () => unknown };

/** Loading, error and empty states for any query, so every list and detail view has all four. */
export function QueryView<T>({ query, empty, isEmpty, rows, children }: { query: QueryLike<T>; empty?: ReactNode; isEmpty?: (d: T) => boolean; rows?: number; children: (data: T) => ReactNode }) {
  if (query.isLoading) return <LoadingState rows={rows} />;
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (query.data === undefined || query.data === null) return <>{empty ?? <EmptyState />}</>;
  if (isEmpty?.(query.data) || (Array.isArray(query.data) && query.data.length === 0)) return <>{empty ?? <EmptyState />}</>;
  return <>{children(query.data)}</>;
}

export function KeyValue({ items, className }: { items: [ReactNode, ReactNode][]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-[minmax(110px,auto)_1fr] gap-x-6 gap-y-2.5 text-sm", className)}>
      {items.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
