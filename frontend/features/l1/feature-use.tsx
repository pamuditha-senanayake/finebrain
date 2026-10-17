"use client";

import { Button } from "@/components/ui/button";
import { SimpleTable } from "@/components/brain/simple-table";
import { Section, StatusChip } from "@/components/brain/primitives";
import { t } from "@/lib/i18n";
import { NAV } from "@/lib/nav";
import { relTime } from "@/lib/format";
import { useUsage } from "@/lib/usage";

/** Which pages people open. Unused pages are the first to remove. */
export function FeatureUse() {
  const opens = useUsage((s) => s.opens);
  const reset = useUsage((s) => s.reset);
  const seen = new Set<string>();
  const rows = NAV.flatMap((a) => a.items.map((i) => ({ area: a.area, href: i.href, label: t(i.label), ...(opens[i.href] ?? { count: 0, lastAt: "" }) })))
    .filter((r) => (seen.has(r.href) ? false : (seen.add(r.href), true)))
    .sort((a, b) => b.count - a.count);
  return (
    <Section
      plain
      className="mt-12"
      title="Feature use"
      description="How often each page is opened in this browser. Pages nobody opens are the first to remove."
      actions={<Button variant="ghost" size="sm" onClick={reset}>Reset</Button>}
    >
      <SimpleTable
        label="Feature use"
        rows={rows}
        getRowId={(r) => r.href}
        columns={[
          { id: "page", header: "Page", className: "font-medium", cell: (r) => r.label },
          { id: "area", header: "Area", className: "w-20 text-muted-foreground", cell: (r) => r.area },
          { id: "opens", header: "Opens", align: "right", className: "w-24 tabular", cell: (r) => (r.count ? r.count : <StatusChip tone="warn">not used</StatusChip>) },
          { id: "last", header: "Last opened", className: "w-36 text-muted-foreground", cell: (r) => (r.lastAt ? relTime(r.lastAt) : "never") },
        ]}
      />
    </Section>
  );
}
