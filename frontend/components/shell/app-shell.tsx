"use client";

import { Brain, Menu, PanelLeftOpen, Search } from "lucide-react";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { BeamScope } from "@/components/brain/motion";
import { DeniedState, LoadingState } from "@/components/brain/primitives";
import { canView, homeFor, useCurrentUser, type Area } from "@/lib/auth";
import { t } from "@/lib/i18n";
import { useUi } from "@/lib/store";
import { navItemFor, useUsage } from "@/lib/usage";
import { cn } from "@/lib/utils";
import { AskOrb } from "./ask-orb";
import { CommandPalette } from "./command-palette";
import { HqOffline } from "./hq-offline";
import { Sidebar, useHoverPeek } from "./sidebar";
import { EnvSwitcher, NotificationsSheet, ShellMenu, TenantClusterSwitcher } from "./widgets";

// How the sidebar moves, open, closed or peeking: one gentle ease so it glides instead of snapping.
const EASE = "300ms cubic-bezier(0.22, 1, 0.36, 1)";
const GROW = `width ${EASE}`;
const SLIDE = `transform ${EASE}, box-shadow ${EASE}`;

export function AppShell({ area, children }: { area: Area; children: ReactNode }) {
  const { user, isLoading, error, retry } = useCurrentUser();
  const setPalette = useUi((s) => s.setPaletteOpen);
  const collapsed = useUi((s) => s.sidebarCollapsed);
  const toggleSidebar = useUi((s) => s.toggleSidebar);
  const [mobileNav, setMobileNav] = useState(false);
  const hover = useHoverPeek(collapsed);
  const open = () => { hover.close(); toggleSidebar(); };
  const allowed = canView(user, area);
  // Full-bleed canvases (maps, graphs, the studio) fill the page. Everything else keeps a readable width, so collapsing the sidebar never stretches tables and cards.
  const pathname = usePathname();
  const fullBleed = /^\/(l1(\/ask)?|studio|l2\/graph|l2\/policies\/.+)\/?$/.test(pathname);
  // Working surfaces with several panes get more room than reading pages.
  const wide = /^\/l3\/conversations(\/.+)?\/?$/.test(pathname);
  // Count page opens so features nobody uses can be found and removed.
  const record = useUsage((s) => s.record);
  useEffect(() => {
    const item = navItemFor(pathname);
    if (item) record(item.href);
  }, [pathname, record]);

  return (
    <BeamScope>
      <div className="flex min-h-dvh flex-col">
        <div className="flex min-h-0 flex-1">
          {/* Open: the sidebar takes its place. Closed: its width slides to nothing, leaving only a thin hover zone on the edge. */}
          <aside className={cn("hidden shrink-0 overflow-x-clip bg-sidebar lg:block", collapsed ? "w-0" : "w-60 border-r")} style={{ transition: GROW }} aria-label="Sidebar" inert={collapsed}>
            <div className="sticky top-0 h-dvh w-60">
              <Sidebar area={area} onToggle={toggleSidebar} />
            </div>
          </aside>
          {collapsed && <div className="fixed inset-y-0 left-0 z-40 hidden w-2 lg:block" onMouseEnter={hover.enter} onMouseLeave={hover.leave} aria-hidden />}
          {/* The hover peek stays mounted while closed, so it slides out and back instead of popping. */}
          {collapsed && (
            <aside className={cn("fixed inset-y-0 left-0 z-50 hidden w-60 border-r bg-sidebar lg:block", hover.peek ? "translate-x-0 shadow-xl" : "pointer-events-none -translate-x-full")} style={{ transition: SLIDE }} aria-label="Sidebar preview" inert={!hover.peek} onMouseEnter={hover.enter} onMouseLeave={hover.leave}>
              <Sidebar area={area} onNavigate={hover.close} onToggle={open} pinned={false} />
            </aside>
          )}
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="sticky top-0 z-30 flex h-12 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur sm:px-4">
              <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setMobileNav(true)} aria-label="Open navigation">
                <Menu />
              </Button>
              {collapsed && (
                // The brand while closed; hovering turns it into the sidebar icon, and a click opens the sidebar.
                <button type="button" onClick={open} className="group relative grid size-8 place-items-center rounded-lg outline-none transition-colors hover:bg-accent focus-visible:ring-4 focus-visible:ring-ring/40 max-lg:hidden" aria-label="Open sidebar" title="Open sidebar" data-testid="sidebar-toggle">
                  <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground transition-opacity duration-200 group-hover:opacity-0 group-focus-visible:opacity-0">
                    <Brain className="size-4" aria-hidden />
                  </span>
                  <PanelLeftOpen className="absolute size-4 text-muted-foreground opacity-0 transition-opacity duration-200 group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden />
                </button>
              )}
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
              {isLoading ? <LoadingState /> : error ? <HqOffline onRetry={retry} /> : !allowed ? <DeniedState reason={user ? `${user.name} (${user.tier}) cannot open ${area === "research" ? "the Research Console" : `${area} ${t(`tier.${area}`)}`}.` : "No persona selected."} home={homeFor(user)} /> : <Suspense fallback={<LoadingState />}>{children}</Suspense>}
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
      <NotificationsSheet />
      <AskOrb />
    </BeamScope>
  );
}
