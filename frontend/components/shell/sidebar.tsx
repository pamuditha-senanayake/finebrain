"use client";

// sidebar.tsx: the left sidebar, like Claude's. Open, an icon beside the brand closes it; closed, nothing shows on the
// left, and the icon in the top bar opens it, or slides it out over the page while hovered. Used by: app-shell.tsx.

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { BrandMark, BrandName } from "@/components/brain/logo";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { canView, useCurrentUser, type Area } from "@/lib/auth";
import { flags } from "@/lib/flags";
import { t } from "@/lib/i18n";
import { AREA_ICON, NAV, RESEARCH_NAV, type NavArea } from "@/lib/nav";
import { cn } from "@/lib/utils";

function useAreas() {
  const { user } = useCurrentUser();
  return [...NAV, ...(flags.research ? [RESEARCH_NAV] : [])].filter((a) => canView(user, a.area));
}

function NavList({ area, onNavigate }: { area: NavArea; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <ul className="space-y-0.5">
      {area.items.map((item, idx) => {
        const newGroup = idx > 0 && (item.group ?? 0) !== (area.items[idx - 1].group ?? 0);
        const under = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
        const active = (item.exact ? pathname === item.href : under(item.href)) || (item.also ?? []).some(under);
        return (
          <li key={item.href} className={cn(newGroup && "mt-2 border-t border-sidebar-border pt-2")}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px] text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                active && "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
              )}
            >
              <item.icon className="size-4 shrink-0" aria-hidden />
              {t(item.label)}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function TierSwitch({ current, onNavigate }: { current: Area; onNavigate?: () => void }) {
  const areas = useAreas();
  if (areas.length < 2) return null;
  return (
    <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${areas.length}, minmax(0, 1fr))` }} role="tablist" aria-label="Tier">
      {areas.map((a) => {
        const Icon = AREA_ICON[a.area];
        return (
          <Link key={a.area} href={a.home} prefetch={false} onClick={onNavigate} role="tab" aria-selected={a.area === current} title={t(a.label)} className={cn("flex flex-col items-center gap-0.5 rounded-lg py-1.5 text-[10px] font-medium text-muted-foreground hover:bg-sidebar-accent", a.area === current && "bg-sidebar-accent text-sidebar-accent-foreground")}>
            <Icon className="size-3.5" aria-hidden />
            {a.area === "research" ? "Research" : a.area}
          </Link>
        );
      })}
    </div>
  );
}

/**
 * The sidebar. On desktop `onToggle` adds the sidebar icon at the top left, before the brand: it closes a pinned
 * sidebar, and pins open one that is only peeking.
 */
export function Sidebar({ area, onNavigate, onToggle, pinned = true }: { area: Area; onNavigate?: () => void; onToggle?: () => void; pinned?: boolean }) {
  const areas = useAreas();
  const current = areas.find((a) => a.area === area) ?? [...NAV, RESEARCH_NAV].find((a) => a.area === area)!;
  return (
    <div className="flex h-full flex-col gap-4 p-3">
      <div className="flex items-center gap-1">
        {onToggle && (
          <Button variant="ghost" size="icon-sm" className="shrink-0 text-muted-foreground" onClick={onToggle} aria-label={pinned ? "Close sidebar" : "Keep sidebar open"} title={pinned ? "Close sidebar" : "Keep sidebar open"}>
            {pinned ? <PanelLeftClose /> : <PanelLeftOpen />}
          </Button>
        )}
        <Link href="/" className="flex min-w-0 items-center gap-2 px-1.5" onClick={onNavigate}>
          <BrandMark className="h-7" />
          <span className="leading-tight">
            <BrandName className="block text-[15px]" />
            <span className="block text-[11px] text-muted-foreground">
              {area === "research" ? t("tier.research") : `${area} · ${t(`tier.${area}`)}`}
            </span>
          </span>
        </Link>
      </div>
      <TierSwitch current={area} onNavigate={onNavigate} />
      <nav aria-label={`${t(current.label)} navigation`} className="min-h-0 flex-1 overflow-auto">
        <NavList area={current} onNavigate={onNavigate} />
      </nav>
    </div>
  );
}

/** While the sidebar is closed, hovering its icon or the left edge slides it out over the page. A short delay on leave lets the pointer cross the gap. */
export function useHoverPeek(enabled: boolean) {
  const [peek, setPeek] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancel = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };
  const enter = () => {
    cancel();
    setPeek(true);
  };
  const leave = () => {
    cancel();
    timer.current = setTimeout(() => setPeek(false), 200);
  };
  useEffect(() => cancel, []);
  return { peek: enabled && peek, enter, leave, close: () => { cancel(); setPeek(false); } };
}
