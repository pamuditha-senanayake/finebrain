"use client";

// home.tsx: the first page. One promise, one way in, and the four areas below. Brand-card look: the crowned mark large
// and faint behind a fine grid, the tagline with a short rule, everything else quiet.
import { ArrowRight, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { BrandMark, BrandName } from "@/components/brain/logo";
import { HqOffline } from "@/components/shell/hq-offline";
import { TenantPicker } from "@/components/shell/tenant-picker";
import { RoleSwitcher, ThemeToggle } from "@/components/shell/widgets";
import { canView, homeFor, useCurrentUser } from "@/lib/auth";
import { flags } from "@/lib/flags";
import { t } from "@/lib/i18n";
import { AREA_ICON, NAV, RESEARCH_NAV, type NavArea } from "@/lib/nav";
import { cn } from "@/lib/utils";

// Config
const BLURB: Record<string, string> = {
  L1: "Progress, risk and approvals.",
  L2: "Skills, policies and knowledge.",
  L3: "Agents at work, live.",
  research: "Metrics, kept apart.",
};
const PRINCIPLES = ["evidence on every fact", "approval follows risk", "nothing goes live blind"];
// A fine grid that fades out from the top, so the page feels technical without getting busy.
const GRID = {
  backgroundImage: "linear-gradient(to right, var(--border) 1px, transparent 1px), linear-gradient(to bottom, var(--border) 1px, transparent 1px)",
  backgroundSize: "56px 56px",
  maskImage: "radial-gradient(ellipse 80% 70% at 50% 0%, black 30%, transparent 75%)",
  WebkitMaskImage: "radial-gradient(ellipse 80% 70% at 50% 0%, black 30%, transparent 75%)",
} as const;

export function Home() {
  const { user, isLoading, error, retry } = useCurrentUser();
  const areas = [...NAV, ...(flags.research ? [RESEARCH_NAV] : [])];
  return (
    <div className="relative isolate min-h-dvh overflow-hidden bg-background">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 opacity-60" style={GRID} />
      <BrandMark className="pointer-events-none absolute -right-16 top-24 -z-10 h-[520px] text-foreground/[0.03] max-md:hidden" />

      <div className="mx-auto flex min-h-dvh max-w-6xl flex-col px-4 sm:px-8">
        {/* Bar: the brand on the left, who and where on the right */}
        <header className="flex h-16 items-center justify-between gap-3">
          <Link href="/" className="flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-4 focus-visible:ring-ring/40" aria-label="FineBrain home">
            <BrandMark className="h-8" />
            <BrandName className="text-xl" />
          </Link>
          <div className="flex items-center gap-1">
            <TenantPicker />
            <ThemeToggle />
            <RoleSwitcher />
          </div>
        </header>

        <main className="flex flex-1 flex-col justify-center py-16">
          {error ? <HqOffline onRetry={retry} /> : (
            <>
              {/* The promise */}
              <p className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.22em] text-primary">
                <span className="h-px w-8 bg-primary" aria-hidden />
                Company brain
              </p>
              <h1 className="mt-6 max-w-3xl text-5xl font-light leading-[1.05] tracking-tight sm:text-7xl">
                Be in two places <span className="whitespace-nowrap font-semibold">at once.</span>
              </h1>
              <p className="mt-6 max-w-xl text-lg text-muted-foreground">Agents run the work. You stay in charge.</p>

              {/* The way in */}
              <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-4">
                {user && (
                  <Link href={homeFor(user)} className="group inline-flex h-12 items-center gap-2 rounded-full bg-primary pl-6 pr-5 text-[15px] font-medium text-primary-foreground shadow-lg shadow-primary/20 outline-none transition-colors hover:bg-primary/90 focus-visible:ring-4 focus-visible:ring-ring/40">
                    Continue as {user.name.split(" ")[0]}
                    <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
                  </Link>
                )}
                <ul className="flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs text-muted-foreground" aria-label="Principles">
                  {PRINCIPLES.map((p) => (
                    <li key={p} className="flex items-center gap-2"><span className="size-1 rounded-full bg-muted-foreground/60" aria-hidden />{p}</li>
                  ))}
                </ul>
              </div>

              {/* The areas */}
              <ul className="mt-20 grid gap-px overflow-hidden rounded-2xl border bg-border sm:grid-cols-2 lg:grid-cols-4">
                {areas.map((a) => <AreaCard key={a.area} area={a} allowed={isLoading || canView(user, a.area)} />)}
              </ul>
            </>
          )}
        </main>

        <footer className="flex h-14 items-center justify-between border-t font-mono text-[11px] text-muted-foreground">
          <span>FineBrain · Finebase Labs</span>
          <span>{user ? `${user.name} · ${user.tier}` : "Not signed in"}</span>
        </footer>
      </div>
    </div>
  );
}

function AreaCard({ area, allowed }: { area: NavArea; allowed: boolean }) {
  const Icon = AREA_ICON[area.area];
  return (
    <li className="bg-background">
      <Link
        href={area.home}
        prefetch={false}
        aria-disabled={!allowed}
        tabIndex={allowed ? undefined : -1}
        className={cn("group flex h-full flex-col gap-6 p-6 outline-none transition-colors hover:bg-accent/50 focus-visible:bg-accent/60", !allowed && "pointer-events-none")}
      >
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-muted-foreground">{area.area === "research" ? "R&D" : area.area}</span>
          <ArrowUpRight className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden />
        </div>
        <Icon className={cn("size-6", allowed ? "text-foreground" : "text-muted-foreground/50")} aria-hidden />
        <div>
          <p className={cn("text-[15px] font-semibold", !allowed && "text-muted-foreground")}>{t(area.label)}</p>
          <p className="mt-1 text-sm text-muted-foreground">{allowed ? BLURB[area.area] : "Not open to your role."}</p>
        </div>
      </Link>
    </li>
  );
}
