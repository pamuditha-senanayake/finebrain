"use client";

import { Brain, Menu, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useState, type ReactNode } from "react";
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
import { ApprovalsCounter, DemoBadge, EnvBanner, EnvSwitcher, NotificationCenter, RoleSwitcher, TenantClusterSwitcher, ThemeToggle } from "./widgets";

function useAreas() {
  const { user } = useCurrentUser();
  return [...NAV, ...(flags.research ? [RESEARCH_NAV] : [])].filter((a) => canView(user, a.area));
}

function NavList({ area, onNavigate }: { area: NavArea; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <ul className="space-y-0.5">
      {area.items.map((item) => {
        const active = item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <li key={item.href}>
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

export function AppShell({ area, children }: { area: Area; children: ReactNode }) {
  const { user, isLoading } = useCurrentUser();
  const setPalette = useUi((s) => s.setPaletteOpen);
  const setAsk = useUi((s) => s.setAskOpen);
  const [mobileNav, setMobileNav] = useState(false);
  const allowed = canView(user, area);

  return (
    <BeamScope>
      <div className="flex min-h-dvh flex-col">
        <EnvBanner />
        <div className="flex min-h-0 flex-1">
          <aside className="hidden w-60 shrink-0 border-r bg-sidebar lg:block" aria-label="Sidebar">
            <div className="sticky top-0 h-[calc(100dvh-1.5rem)]">
              <Sidebar area={area} />
            </div>
          </aside>
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="sticky top-0 z-30 flex h-12 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur sm:px-4">
              <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setMobileNav(true)} aria-label="Open navigation">
                <Menu />
              </Button>
              <TenantClusterSwitcher />
              <div className="max-md:hidden">
                <EnvSwitcher />
              </div>
              <button
                type="button"
                onClick={() => setPalette(true)}
                className="ml-auto flex h-8 items-center gap-2 rounded-lg border bg-surface px-2.5 text-xs text-muted-foreground hover:bg-accent sm:ml-2 sm:min-w-[220px]"
                aria-label="Open command palette"
              >
                <Search className="size-3.5" aria-hidden />
                <span className="max-sm:hidden">{t("shell.search")}</span>
                <kbd className="ml-auto rounded border bg-background px-1 font-mono text-[10px] max-sm:hidden">⌘K</kbd>
              </button>
              <div className="flex items-center gap-1 sm:ml-auto">
                <Button variant="ghost" size="sm" className="h-8 gap-1.5" onClick={() => setAsk(true)} aria-label={t("shell.ask")}>
                  <Sparkles className="text-primary" />
                  <span className="text-xs max-md:hidden">{t("shell.ask")}</span>
                </Button>
                <div className="max-sm:hidden">
                  <ApprovalsCounter />
                </div>
                <NotificationCenter />
                <ThemeToggle />
                <div className="max-sm:hidden">
                  <DemoBadge />
                </div>
                <RoleSwitcher />
              </div>
            </header>
            <main id="main" className="mx-auto w-full max-w-[1600px] flex-1 px-3 py-4 sm:px-6 sm:py-5">
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
    </BeamScope>
  );
}
