"use client";

import { ArrowRight, Brain } from "lucide-react";
import Link from "next/link";
import { AmbientSurface } from "@/components/brain/motion";
import { RoleSwitcher, ThemeToggle } from "@/components/shell/widgets";
import { canView, homeFor, useCurrentUser } from "@/lib/auth";
import { flags } from "@/lib/flags";
import { t } from "@/lib/i18n";
import { AREA_ICON, NAV, RESEARCH_NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";

const BLURB: Record<string, string> = {
  L1: "Progress, risk, approvals and evidence across every cluster.",
  L2: "Skills, policies, security, templates and the knowledge graph.",
  L3: "Agents at work. Watch, inspect, take over and resolve.",
  research: "Read only research metrics, separate from the product.",
};

export function Home() {
  const { user } = useCurrentUser();
  const areas = [...NAV, ...(flags.research ? [RESEARCH_NAV] : [])];
  return (
    <AmbientSurface className="min-h-dvh">
      <div className="relative mx-auto flex min-h-dvh max-w-5xl flex-col px-4 py-8 sm:px-6">
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">
              <Brain className="size-4" aria-hidden />
            </span>
            <span className="font-semibold">{t("app.name")}</span>
          </div>
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <RoleSwitcher />
          </div>
        </header>
        <main className="my-auto py-10">
          <h1 className="max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">A governed layer where agents run the work and people stay in charge.</h1>
          <p className="mt-3 max-w-2xl text-muted-foreground">Every fact carries its evidence. Nothing goes live blind. Approval weight follows criticality.</p>
          {user && (
            <Link href={homeFor(user)} className="mt-6 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
              Continue as {user.name} <ArrowRight className="size-4" />
            </Link>
          )}
          <ul className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {areas.map((a) => {
              const Icon = AREA_ICON[a.area];
              const allowed = canView(user, a.area);
              return (
                <li key={a.area}>
                  <Link href={a.home} prefetch={false} aria-disabled={!allowed} className={cn("block h-full rounded-xl border bg-card/80 p-4 backdrop-blur transition-colors hover:border-primary/50", !allowed && "pointer-events-none opacity-50")}>
                    <Icon className="mb-3 size-5 text-primary" aria-hidden />
                    <div className="text-sm font-semibold">
                      {a.area === "research" ? "" : `${a.area} · `}
                      {t(a.label)}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{BLURB[a.area]}</p>
                    {!allowed && <p className="mt-2 text-[11px] text-muted-foreground">Not available to your persona</p>}
                  </Link>
                </li>
              );
            })}
          </ul>
        </main>
      </div>
    </AmbientSurface>
  );
}
