"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

/** Graph and its versions share one nav item; this switch moves between them. */
export function GraphTabs({ className }: { className?: string }) {
  const pathname = usePathname();
  const onVersions = pathname.startsWith("/l2/versioning");
  const tab = (href: string, label: string, active: boolean) => (
    <Link href={href} aria-current={active ? "page" : undefined} className={cn("rounded-full px-3.5 py-1 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground", active && "bg-sidebar-accent text-foreground")}>
      {label}
    </Link>
  );
  return (
    <nav aria-label="Graph or versions" className={cn("inline-flex items-center gap-0.5 rounded-full border bg-card/90 p-0.5 shadow-sm backdrop-blur", className)}>
      {tab("/l2/graph", "Graph", !onVersions)}
      {tab("/l2/versioning", "Versions", onVersions)}
    </nav>
  );
}
