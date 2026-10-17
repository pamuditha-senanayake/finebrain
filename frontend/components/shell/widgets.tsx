"use client";

import { Bell, Check, ChevronDown, Inbox, Monitor, Moon, RotateCcw, Sun, UserCog } from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import type { Env } from "@/contracts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApprovals, useBranches, useClusters, useHumans, useNotifications, useOp, useTenants } from "@/lib/api/hooks";
import { canView, homeFor, useCurrentUser } from "@/lib/auth";
import { flags } from "@/lib/flags";
import { initials, textOn, relTime } from "@/lib/format";
import { t } from "@/lib/i18n";
import { DEFAULT_PERSONA, useUi } from "@/lib/store";
import { cn } from "@/lib/utils";
import { CritBadge } from "@/components/brain/primitives";

export function EnvBanner() {
  const env = useUi((s) => s.env);
  const cls = env.kind === "production" ? "bg-env-production text-white" : env.kind === "staging" ? "bg-env-staging text-black" : "bg-env-sandbox text-white";
  const label = env.kind === "sandbox" ? t("env.sandbox", { branch: env.branch }) : t(`env.${env.kind}`);
  return (
    <div className={cn("flex h-6 items-center justify-center gap-2 text-[11px] font-bold tracking-wider", cls)} role="status" aria-label={`Environment: ${label}`} data-testid="env-banner">
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {label}
    </div>
  );
}

export function EnvSwitcher() {
  const env = useUi((s) => s.env);
  const setEnv = useUi((s) => s.setEnv);
  const branches = useBranches();
  const sandboxes = (branches.data ?? []).filter((b) => b.env === "sandbox" && b.status === "open");
  const value = env.kind === "sandbox" ? `sandbox:${env.branch}` : env.kind;
  return (
    <Select
      value={value}
      onValueChange={(v) => {
        if (v.startsWith("sandbox:")) setEnv("sandbox", v.slice(8));
        else setEnv(v as Env);
      }}
    >
      <SelectTrigger size="sm" className="h-8 w-[150px] text-xs" aria-label="Environment">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="production">Production</SelectItem>
        <SelectItem value="staging">Staging (shadow)</SelectItem>
        {sandboxes.map((b) => (
          <SelectItem key={b.id} value={`sandbox:${b.name}`}>
            {b.name.replace("sandbox/", "Sandbox · ")}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function TenantClusterSwitcher() {
  const tenantId = useUi((s) => s.tenantId);
  const clusterId = useUi((s) => s.clusterId);
  const setTenant = useUi((s) => s.setTenant);
  const setCluster = useUi((s) => s.setCluster);
  const tenants = useTenants();
  const clusters = useClusters();
  const router = useRouter();
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <Select
        value={tenantId}
        onValueChange={(v) => {
          setTenant(v);
          router.push(homeFor(null));
        }}
      >
        <SelectTrigger size="sm" className="h-8 max-w-[160px] text-xs font-medium" aria-label="Tenant">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(tenants.data ?? [{ id: tenantId, name: tenantId, isScaleDemo: false }]).map((tn) => (
            <SelectItem key={tn.id} value={tn.id}>
              {tn.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={clusterId} onValueChange={setCluster}>
        <SelectTrigger size="sm" className="h-8 max-w-[190px] text-xs max-md:hidden" aria-label="Cluster">
          <SelectValue placeholder="All clusters" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All clusters</SelectItem>
          {(clusters.data ?? []).map((c) => (
            <SelectItem key={c.id} value={c.id} disabled={c.status === "planned"}>
              {c.name}
              {c.status === "planned" && <span className="ml-1 text-[10px] text-muted-foreground">planned</span>}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

/** Approvals this person can act on: their tier, their DRI work or delegated to them, inside their ceiling. */
export function useMyApprovals() {
  const approvals = useApprovals();
  const { user } = useCurrentUser();
  const mine = (approvals.data ?? []).filter((a) => a.status === "pending" && user && (a.requiredApprovers.tier === user.tier || a.dri === user.id || a.delegatedTo === user.id) && user.maxApprovalCriticality >= a.criticality);
  return { mine, canApprove: !!user && user.tier !== "L3", isLoading: approvals.isLoading };
}

export function useMyNotifications() {
  const notifications = useNotifications();
  const { user } = useCurrentUser();
  const list = (notifications.data ?? []).filter((n) => !n.to || n.to === user?.id);
  return { list, unread: list.filter((n) => !n.read).length };
}

/** Notifications in a side sheet, opened from the shell menu or the L1 status box. */
export function NotificationsSheet() {
  const open = useUi((st) => st.notificationsOpen);
  const setOpen = useUi((st) => st.setNotificationsOpen);
  const { list, unread } = useMyNotifications();
  const markRead = useOp<{ id: string }>("markRead", { silent: true });
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent className="w-full gap-0 p-0 sm:max-w-sm">
        <SheetHeader className="flex-row items-center justify-between border-b px-4 py-3">
          <SheetTitle className="flex items-center gap-2 text-sm"><Bell className="size-4" /> {t("shell.notifications")}</SheetTitle>
          <SheetDescription className="sr-only">{unread} unread</SheetDescription>
          <Button variant="ghost" size="xs" className="mr-8" onClick={() => markRead.mutate({ id: "all" })} disabled={!unread}>
            <Check /> Mark all read
          </Button>
        </SheetHeader>
        <ul className="min-h-0 flex-1 overflow-auto" aria-live="polite">
          {list.length === 0 && <li className="p-4 text-center text-xs text-muted-foreground">Nothing new</li>}
          {list.slice(0, 40).map((n) => (
            <li key={n.id}>
              <Link href={n.href} onClick={() => { if (!n.read) markRead.mutate({ id: n.id }); setOpen(false); }} className={cn("block border-b px-4 py-2.5 text-sm last:border-0 hover:bg-accent", !n.read && "bg-primary/5")}>
                <div className="flex items-start gap-2">
                  {!n.read && <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" aria-label="unread" />}
                  <div className="min-w-0">
                    <div className="font-medium">{n.title}</div>
                    <div className="truncate text-xs text-muted-foreground">{n.body}</div>
                    <div className="mt-0.5 text-[10px] text-muted-foreground">{relTime(n.at)}</div>
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </SheetContent>
    </Sheet>
  );
}

/** The one menu left in the top bar: theme, approvals, notifications and demo data. Personas switch on the home page. */
export function ShellMenu() {
  const { user } = useCurrentUser();
  const { theme, setTheme } = useTheme();
  const { mine, canApprove } = useMyApprovals();
  const { unread } = useMyNotifications();
  const setNotifications = useUi((st) => st.setNotificationsOpen);
  const qc = useQueryClient();
  const router = useRouter();
  if (!user) return null;
  const alerts = unread + (canApprove ? mine.length : 0);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="relative h-9 gap-1.5 px-1.5" aria-label={`Menu for ${user.name}${alerts ? `, ${alerts} items need you` : ""}`} data-testid="shell-menu">
          <span className="grid size-7 place-items-center rounded-full text-[10px] font-semibold" style={{ background: user.color, color: textOn(user.color) }} aria-hidden>
            {initials(user.name)}
          </span>
          {alerts > 0 && <span className="absolute left-7 top-1 size-2 rounded-full bg-risk ring-2 ring-background" aria-hidden />}
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="leading-tight">
          <span className="block text-sm">{user.name}</span>
          <span className="block text-[11px] font-normal text-muted-foreground">{user.tier} · {user.title}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {canApprove && (
          <DropdownMenuItem onSelect={() => router.push("/l1/digest?tab=approvals")} data-testid="menu-approvals">
            <Inbox /> Approvals
            <Badge variant={mine.length ? "default" : "secondary"} className="ml-auto tabular" data-testid="approvals-count">{mine.length}</Badge>
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onSelect={() => setNotifications(true)}>
          <Bell /> {t("shell.notifications")}
          {unread > 0 && <Badge className="ml-auto tabular">{unread}</Badge>}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme ?? "system"} onValueChange={setTheme}>
          <DropdownMenuRadioItem value="light"><Sun /> Light</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark"><Moon /> Dark, warm</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="black"><Moon className="fill-current" /> Dark, black</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system"><Monitor /> System</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        {flags.mocks && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={async () => {
                await fetch("/api/mock/reset", { method: "POST" });
                qc.invalidateQueries();
              }}
            >
              <RotateCcw /> {t("demo.reset")}
              <span className="ml-auto rounded border border-dashed border-warn/60 px-1 text-[9px] font-semibold uppercase text-warn-fg">{t("demo.badge")}</span>
            </DropdownMenuItem>
          </>
        )}
        {flags.roleSwitcher && (
          <DropdownMenuItem onSelect={() => router.push("/")}>
            <UserCog /> Switch persona on the home page
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function RoleSwitcher() {
  const humans = useHumans();
  const { user } = useCurrentUser();
  const setPersona = useUi((s) => s.setPersona);
  const tenantId = useUi((s) => s.tenantId);
  const router = useRouter();
  const pathname = usePathname();
  const qc = useQueryClient();
  if (!user) return null;
  const trigger = (
    <span className="flex items-center gap-2">
      <span className="grid size-6 place-items-center rounded-full text-[10px] font-semibold" style={{ background: user.color, color: textOn(user.color) }} aria-hidden>
        {initials(user.name)}
      </span>
      <span className="hidden text-left leading-tight lg:block">
        <span className="block text-xs font-medium">{user.name}</span>
        <span className="block text-[10px] text-muted-foreground">
          {user.tier} · {user.title}
        </span>
      </span>
      {flags.roleSwitcher && <ChevronDown className="size-3.5 text-muted-foreground" />}
    </span>
  );
  if (!flags.roleSwitcher) return <div className="px-2">{trigger}</div>;
  const groups = (["L1", "L2", "L3"] as const).map((tier) => ({ tier, people: (humans.data ?? []).filter((h) => h.tier === tier) }));
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-9 gap-2 px-2" aria-label={`${t("shell.persona")} ${user.name}. Switch persona`} data-testid="role-switcher">
          {trigger}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="flex items-center gap-2 text-xs">
          <UserCog className="size-3.5" /> Impersonate a persona (dev and demo only)
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {groups.map((g) => (
          <DropdownMenuGroup key={g.tier}>
            <DropdownMenuLabel className="text-[10px] uppercase tracking-wide text-muted-foreground">{g.tier} · {t(`tier.${g.tier}`)}</DropdownMenuLabel>
            {g.people.map((h) => (
              <DropdownMenuItem
                key={h.id}
                data-testid={`persona-${h.id}`}
                onSelect={() => {
                  setPersona(h.id);
                  qc.invalidateQueries({ queryKey: ["t", tenantId] });
                  const area = pathname.startsWith("/l1") ? "L1" : pathname.startsWith("/l2") ? "L2" : pathname.startsWith("/l3") ? "L3" : pathname.startsWith("/research") ? "research" : null;
                  if (pathname !== "/" && (!area || !canView(h, area))) router.push(homeFor(h));
                }}
              >
                <span className="grid size-5 place-items-center rounded-full text-[9px] font-semibold" style={{ background: h.color, color: textOn(h.color) }} aria-hidden>
                  {initials(h.name)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{h.name}</span>
                  <span className="block truncate text-[11px] text-muted-foreground">{h.title}</span>
                </span>
                {h.maxApprovalCriticality > 0 && <CritBadge level={h.maxApprovalCriticality} />}
                {h.id === user.id && <Check className="size-3.5" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => setPersona(DEFAULT_PERSONA[tenantId])}>Back to default persona</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <Button variant="ghost" size="icon-sm" onClick={() => setTheme(resolvedTheme === "dark" || resolvedTheme === "black" ? "light" : "dark")} aria-label="Toggle light and dark theme">
      <Sun className="hidden dark:block" />
      <Moon className="dark:hidden" />
    </Button>
  );
}

export function DemoBadge() {
  const qc = useQueryClient();
  if (!flags.mocks) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className="rounded-md border border-dashed border-warn/60 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-warn-fg" data-testid="demo-badge">
          {t("demo.badge")}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Mock API and seed data. Your edits are kept in this browser.</DropdownMenuLabel>
        <DropdownMenuItem
          onSelect={async () => {
            await fetch("/api/mock/reset", { method: "POST" });
            qc.invalidateQueries();
          }}
        >
          <RotateCcw /> {t("demo.reset")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
