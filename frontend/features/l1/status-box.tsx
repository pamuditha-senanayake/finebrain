"use client";

import { Bell, ChevronDown, Coins, Inbox, ShieldAlert, Siren } from "lucide-react";
import Link from "next/link";
import { useId, useMemo, useState, type ReactNode } from "react";
import type { Overview } from "@/contracts";
import { useMyApprovals, useMyNotifications } from "@/components/shell/widgets";
import { useTenant } from "@/lib/api/hooks";
import { usd } from "@/lib/format";
import { t } from "@/lib/i18n";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";

/** Agent runs as a live line, not a number: every 30 minute slot of the last day, the last one still filling. */
function RunsSpark({ series, running }: { series: Overview["runSeries"]; running: number }) {
  const id = useId();
  const { path, area, last, peak } = useMemo(() => {
    const w = 188;
    const h = 38;
    const max = Math.max(1, ...series.map((s) => s.runs));
    const pts = series.map((s, i) => [(i / Math.max(1, series.length - 1)) * w, h - 3 - (s.runs / max) * (h - 8)] as const);
    const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
    return { path: d, area: `${d} L${w},${h} L0,${h} Z`, last: pts[pts.length - 1] ?? [w, h], peak: max };
  }, [series]);
  const now = series[series.length - 1]?.runs ?? 0;
  return (
    <div>
      <div className="flex items-baseline justify-between text-[11px]">
        <span className="text-muted-foreground">Agent runs · 24h</span>
        <span className="tabular"><span className="font-semibold">{running}</span> <span className="text-muted-foreground">running</span></span>
      </div>
      <svg viewBox="0 0 188 38" className="mt-1 h-10 w-full overflow-visible" role="img" aria-label={`Agent runs over the last 24 hours, peak ${peak} per half hour, ${now} in the current half hour, ${running} running now`}>
        <defs>
          <linearGradient id={`${id}-g`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.35} />
            <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <path d={area} fill={`url(#${id}-g)`} />
        <path d={path} fill="none" stroke="var(--primary)" strokeWidth={1.5} strokeLinejoin="round" />
        <circle cx={last[0]} cy={last[1]} r={2.5} fill="var(--primary)" className="spark-ping" />
        <circle cx={last[0]} cy={last[1]} r={2.5} fill="var(--primary)" />
      </svg>
    </div>
  );
}

function Row({ icon, label, value, tone, href, onClick, hint }: { icon: ReactNode; label: string; value: ReactNode; tone?: "risk" | "warn" | "ok"; href?: string; onClick?: () => void; hint?: string }) {
  const body = (
    <>
      <span className="text-muted-foreground [&>svg]:size-3.5" aria-hidden>{icon}</span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {hint && <span className="text-[10px] text-muted-foreground">{hint}</span>}
      <span className={cn("tabular font-semibold", tone === "risk" && "text-risk", tone === "warn" && "text-warn-fg", tone === "ok" && "text-ok")}>{value}</span>
    </>
  );
  const cls = "flex min-h-7 w-full items-center gap-2 rounded-md px-1.5 text-xs transition-colors hover:bg-accent";
  if (href) return <Link href={href} className={cls}>{body}</Link>;
  if (onClick) return <button type="button" onClick={onClick} className={cls}>{body}</button>;
  return <div className={cls}>{body}</div>;
}

function delta(now: number, prev: number) {
  if (!prev) return null;
  const d = (now - prev) / prev;
  return `${d >= 0 ? "+" : ""}${Math.round(d * 100)}%`;
}

/** One small box with only what an L1 needs at a glance. Everything else lives on its own page. */
export function StatusBox({ o }: { o: Overview }) {
  const [open, setOpen] = useState(true);
  const env = useUi((s) => s.env);
  const setNotifications = useUi((s) => s.setNotificationsOpen);
  const tenant = useTenant();
  const { mine, canApprove } = useMyApprovals();
  const { unread } = useMyNotifications();
  const envLabel = env.kind === "sandbox" ? t("env.sandbox", { branch: env.branch }) : t(`env.${env.kind}`);
  const envCls = env.kind === "production" ? "bg-env-production text-white" : env.kind === "staging" ? "bg-env-staging text-black" : "bg-env-sandbox text-white";
  const weekDelta = delta(o.costs.weekUsd, o.costs.prevWeekUsd);
  return (
    <section className="w-full rounded-2xl border bg-card/90 shadow-lg backdrop-blur" aria-label="Brain status">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left" aria-expanded={open}>
        <span className={cn("inline-flex h-5 items-center gap-1.5 rounded-full px-2 text-[10px] font-bold tracking-wider", envCls)} data-testid="env-banner">
          <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden />
          {envLabel}
        </span>
        <ChevronDown className={cn("ml-auto size-3.5 text-muted-foreground transition-transform", !open && "-rotate-90")} aria-hidden />
        <span className="sr-only">{open ? "Collapse" : "Expand"} brain status</span>
      </button>
      {open && (
        <div className="space-y-2 border-t px-2 pb-2 pt-2">
          <p className="px-1.5 text-[10px] text-muted-foreground">{tenant.data?.name ?? ""} · {o.totals.activeAgents} agents working · {o.totals.autonomyRate ? `${Math.round(o.totals.autonomyRate * 100)}% autonomous` : ""}</p>
          <div className="px-1.5">
            <RunsSpark series={o.runSeries} running={o.runningNow} />
          </div>
          <div className="space-y-0.5">
            <Row icon={<Siren />} label="Open risks" value={o.totals.openRisks} tone={o.totals.openRisks > 5 ? "risk" : o.totals.openRisks ? "warn" : "ok"} href="/l1/entity" />
            {canApprove && <Row icon={<Inbox />} label="Approvals" value={mine.length} tone={mine.length ? "warn" : undefined} href="/l1/digest?tab=approvals" />}
            <Row icon={<Bell />} label={t("shell.notifications")} value={unread} tone={unread ? "warn" : undefined} onClick={() => setNotifications(true)} hint={unread ? "unread" : undefined} />
            <Row icon={<ShieldAlert />} label="Entity protection" value={o.entity.red + o.entity.amber} tone={o.entity.red ? "risk" : o.entity.amber ? "warn" : "ok"} href="/l1/entity" hint={`${o.entity.red} red · ${o.entity.amber} amber`} />
            <Row icon={<Coins />} label="Cost, last 7 days" value={usd(o.costs.weekUsd)} hint={weekDelta ?? undefined} href="/l1/analytics" />
            <Row icon={<Coins />} label="Cost, last 30 days" value={usd(o.costs.monthUsd)} href="/l1/analytics" />
          </div>
        </div>
      )}
    </section>
  );
}
