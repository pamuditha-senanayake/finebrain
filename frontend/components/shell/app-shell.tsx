"use client";

import { Brain, Menu, PanelLeftClose, PanelLeftOpen, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { BeamScope } from "@/components/brain/motion";
import { DeniedState, LoadingState } from "@/components/brain/primitives";
import { canView, homeFor, useCurrentUser, type Area } from "@/lib/auth";
import { flags } from "@/lib/flags";
import { t } from "@/lib/i18n";
import { AREA_ICON, NAV, RESEARCH_NAV, type NavArea } from "@/lib/nav";
import { useUi } from "@/lib/store";
import { cn } from "@/lib/utils";
import { AskPanel } from "./ask-panel";
import { CommandPalette } from "./command-palette";
import { EnvSwitcher, NotificationsSheet, ShellMenu, TenantClusterSwitcher } from "./widgets";

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
        const active = item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
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

function Sidebar({ area, onNavigate }: { area: Area; onNavigate?: () => void }) {
  const areas = useAreas();
  const current = areas.find((a) => a.area === area) ?? [...NAV, RESEARCH_NAV].find((a) => a.area === area)!;
  return (
    <div className="flex h-full flex-col gap-4 p-3">
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
      <TierSwitch current={area} onNavigate={onNavigate} />
      <nav aria-label={`${t(current.label)} navigation`} className="min-h-0 flex-1 overflow-auto">
        <NavList area={current} onNavigate={onNavigate} />
      </nav>
    </div>
  );
}

/** Ask the Brain floats bottom right on every page. Workflow Studio has its own assistant and the Ask the Brain page is the full version, so it steps aside on both. */
function AskFab() {
  const setAsk = useUi((s) => s.setAskOpen);
  const pathname = usePathname();
  if (pathname.startsWith("/studio") || pathname.startsWith("/l1/ask")) return null;
  return (
    <button
      type="button"
      onClick={() => setAsk(true)}
      className="fixed bottom-4 right-4 z-40 inline-flex items-center gap-2 rounded-2xl border border-primary/30 bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-lg shadow-primary/25 transition hover:-translate-y-0.5 hover:shadow-xl focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 sm:bottom-6 sm:right-6"
      aria-label={t("shell.ask")}
    >
      <Sparkles className="size-4" aria-hidden />
      {t("shell.ask")}
    </button>
  );
}

/** While the sidebar is collapsed, hovering the toggle slides it out as an overlay. No click needed. */
function useHoverPeek(enabled: boolean) {
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
    timer.current = setTimeout(() => setPeek(false), 150);
  };
  useEffect(() => cancel, []);
  return { peek: enabled && peek, enter, leave, close: () => { cancel(); setPeek(false); } };
}

export function AppShell({ area, children }: { area: Area; children: ReactNode }) {
  const { user, isLoading } = useCurrentUser();
  const setPalette = useUi((s) => s.setPaletteOpen);
  const collapsed = useUi((s) => s.sidebarCollapsed);
  const toggleSidebar = useUi((s) => s.toggleSidebar);
  const [mobileNav, setMobileNav] = useState(false);
  const hover = useHoverPeek(collapsed);
  const allowed = canView(user, area);
  // Full-bleed canvases (maps, graphs, the studio) fill the page. Everything else keeps a readable width, so collapsing the sidebar never stretches tables and cards.
  const pathname = usePathname();
  const fullBleed = /^\/(l1|studio|l2\/graph|l2\/policies\/.+)\/?$/.test(pathname);
  // Working surfaces with several panes get more room than reading pages.
  const wide = /^\/l3\/conversations(\/.+)?\/?$/.test(pathname);

  return (
    <BeamScope>
      <div className="flex min-h-dvh flex-col">
        <div className="flex min-h-0 flex-1">
          <aside className={cn("hidden w-60 shrink-0 border-r bg-sidebar", !collapsed && "lg:block")} aria-label="Sidebar">
            <div className="sticky top-0 h-dvh">
              <Sidebar area={area} />
            </div>
          </aside>
          {hover.peek && (
            <aside
              className="fixed bottom-0 left-0 top-12 z-40 hidden w-60 border-r bg-sidebar shadow-xl animate-in slide-in-from-left-4 fade-in-0 duration-150 lg:block"
              aria-label="Sidebar preview"
              onMouseEnter={hover.enter}
              onMouseLeave={hover.leave}
            >
              <Sidebar area={area} onNavigate={hover.close} />
            </aside>
          )}
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="sticky top-0 z-30 flex h-12 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur sm:px-4">
              <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setMobileNav(true)} aria-label="Open navigation">
                <Menu />
              </Button>
              <Button variant="ghost" size="icon-sm" className="max-lg:hidden" onClick={() => { hover.close(); toggleSidebar(); }} onMouseEnter={hover.enter} onMouseLeave={hover.leave} onFocus={hover.enter} aria-label={collapsed ? "Show sidebar" : "Hide sidebar"} aria-pressed={!collapsed} data-testid="sidebar-toggle">
                {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
              </Button>
              <TenantClusterSwitcher />
              <div className="max-md:hidden">
                <EnvSwitcher />
              </div>
              <button
                type="button"
                onClick={() => setPalette(true)}
                className="ml-auto flex h-8 items-center gap-2 rounded-lg border bg-surface px-2.5 text-xs text-muted-foreground hover:bg-accent sm:min-w-[220px]"
                aria-label="Open command palette"
              >
                <Search className="size-3.5" aria-hidden />
                <span className="max-sm:hidden">{t("shell.search")}</span>
                <kbd className="ml-auto rounded border bg-background px-1 font-mono text-[10px] max-sm:hidden">⌘K</kbd>
              </button>
              <ShellMenu />
            </header>
            <main id="main" className={cn("w-full flex-1", fullBleed ? "px-3 py-4 sm:px-6 sm:py-5" : cn("mx-auto px-4 pb-16 pt-8 sm:px-8 sm:pt-10 lg:px-10", wide ? "max-w-[1440px]" : "max-w-[1120px]"))}>
              {isLoading ? <LoadingState /> : !allowed ? <DeniedState reason={user ? `${user.name} (${user.tier}) cannot open ${area === "research" ? "the Research Console" : `${area} ${t(`tier.${area}`)}`}.` : "No persona selected."} home={homeFor(user)} /> : <Suspense fallback={<LoadingState />}>{children}</Suspense>}
            </main>
          </div>
        </div>
      </div>
      <Sheet open={mobileNav} onOpenChange={setMobileNav}>
        <SheetContent side="left" className="w-72 bg-sidebar p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Navigation</SheetTitle>
          </SheetHeader>
          <Sidebar area={area} onNavigate={() => setMobileNav(false)} />
        </SheetContent>
      </Sheet>
      <CommandPalette />
      <AskPanel />
      <NotificationsSheet />
      <AskFab />
    </BeamScope>
  );
}
