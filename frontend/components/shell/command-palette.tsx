"use client";

import { ArrowRight, Moon, RotateCcw, Sparkles, UserCog } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from "@/components/ui/command";
import { useHumans, useSearch } from "@/lib/api/hooks";
import { canView, useCurrentUser } from "@/lib/auth";
import { flags } from "@/lib/flags";
import { t } from "@/lib/i18n";
import { NAV, RESEARCH_NAV } from "@/lib/nav";
import { useUi } from "@/lib/store";

export function CommandPalette() {
  const open = useUi((s) => s.paletteOpen);
  const setOpen = useUi((s) => s.setPaletteOpen);
  const setAsk = useUi((s) => s.setAskOpen);
  const setPersona = useUi((s) => s.setPersona);
  const [q, setQ] = useState("");
  const router = useRouter();
  const { user } = useCurrentUser();
  const humans = useHumans();
  const hits = useSearch(q);
  const { resolvedTheme, setTheme } = useTheme();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!useUi.getState().paletteOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  const go = (href: string) => {
    setOpen(false);
    setQ("");
    router.push(href);
  };
  const areas = [...NAV, ...(flags.research ? [RESEARCH_NAV] : [])].filter((a) => canView(user, a.area));

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title="Command palette" description="Navigate, search entities and run actions">
      <Command>
      <CommandInput placeholder={t("shell.search")} value={q} onValueChange={setQ} />
      <CommandList>
        <CommandEmpty>{hits.isFetching ? "Searching…" : "No results"}</CommandEmpty>
        {(hits.data ?? []).length > 0 && (
          <CommandGroup heading="Entities">
            {hits.data!.map((h) => (
              <CommandItem key={`${h.kind}-${h.id}`} value={`${h.kind} ${h.label} ${h.id}`} onSelect={() => go(h.href)}>
                <span className="w-20 shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground">{h.kind}</span>
                <span className="truncate">{h.label}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {areas.map((a) => (
          <CommandGroup key={a.area} heading={t(a.label)}>
            {a.items.map((item) => (
              <CommandItem key={item.href} value={`${t(a.label)} ${t(item.label)}`} onSelect={() => go(item.href)}>
                <item.icon /> {t(item.label)}
                <ArrowRight className="ml-auto opacity-40" />
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
        <CommandSeparator />
        <CommandGroup heading="Actions">
          <CommandItem
            value="ask the brain"
            onSelect={() => {
              setOpen(false);
              setAsk(true);
            }}
          >
            <Sparkles /> {t("shell.ask")}
          </CommandItem>
          <CommandItem value="toggle theme dark light" onSelect={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
            <Moon /> Toggle theme
          </CommandItem>
          <CommandItem
            value="reset demo data"
            onSelect={async () => {
              await fetch("/api/mock/reset", { method: "POST" });
              location.reload();
            }}
          >
            <RotateCcw /> {t("demo.reset")}
          </CommandItem>
        </CommandGroup>
        {flags.roleSwitcher && (
          <CommandGroup heading="Switch persona">
            {(humans.data ?? []).map((h) => (
              <CommandItem
                key={h.id}
                value={`persona ${h.name} ${h.title} ${h.tier}`}
                onSelect={() => {
                  setPersona(h.id);
                  setOpen(false);
                }}
              >
                <UserCog /> {h.name} <span className="text-xs text-muted-foreground">{h.tier} · {h.title}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
      </Command>
    </CommandDialog>
  );
}
