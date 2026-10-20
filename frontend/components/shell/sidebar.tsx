"use client";

// sidebar.tsx: the left sidebar. Open it shows the brand, a close button, the tier switch and the pages; closed it is
// a thin rail with only the brand icon, which opens it again. Used by: app-shell.tsx.

import { Brain, PanelLeftClose } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
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

/** The open sidebar. On desktop `onCollapse` adds the close button at the top right, beside the brand. */
export function Sidebar({ area, onNavigate, onCollapse }: { area: Area; onNavigate?: () => void; onCollapse?: () => void }) {
  const areas = useAreas();
  const current = areas.find((a) => a.area === area) ?? [...NAV, RESEARCH_NAV].find((a) => a.area === area)!;
  return (
    <div className="relative flex h-full flex-col gap-4 p-3">
      <Link href="/" className="flex items-center gap-2 px-1.5" onClick={onNavigate}>
        <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground">
          <Brain className="size-4" aria-hidden />
        </span>
        <span className="leading-tight">
          <span className="block text-sm font-semibold">{t("app.name")}</span>
          <span className="block text-[11px] text-muted-foreground">
            {area === "research" ? t("tier.research") : `${area} · ${t(`tier.${area}`)}`}
          </span>
        </span>
      </Link>
      {onCollapse && (
        <Button variant="ghost" size="icon-sm" className="absolute right-3 top-3 text-muted-foreground" onClick={onCollapse} aria-label="Hide sidebar" title="Hide sidebar" data-testid="sidebar-toggle">
          <PanelLeftClose />
        </Button>
      )}
      <TierSwitch current={area} onNavigate={onNavigate} />
      <nav aria-label={`${t(current.label)} navigation`} className="min-h-0 flex-1 overflow-auto">
        <NavList area={current} onNavigate={onNavigate} />
      </nav>
    </div>
  );
}

/** The closed sidebar: only the brand icon. Clicking it opens the sidebar. */
export function SidebarRail({ onExpand }: { onExpand: () => void }) {
  return (
    <div className="flex h-full flex-col items-center p-3">
      <button type="button" onClick={onExpand} className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground outline-none transition-transform hover:scale-105 focus-visible:ring-4 focus-visible:ring-ring/40" aria-label="Show sidebar" title="Show sidebar" data-testid="sidebar-expand">
        <Brain className="size-4" aria-hidden />
      </button>
    </div>
  );
}
