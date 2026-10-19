"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/** Dropdown filter with a count per option. The value "all" means no filter. */
export function CategoryFilter({ label, allLabel, value, onChange, options, className, labelOf }: { label: string; allLabel: string; value: string; onChange: (v: string) => void; options: { value: string; count: number }[]; className?: string; labelOf?: (value: string) => string }) {
  const total = options.reduce((s, o) => s + o.count, 0);
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger size="sm" className={className ?? "w-[200px] text-xs"} aria-label={label}>
        <SelectValue placeholder={allLabel} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">{allLabel} ({total})</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value} className="capitalize">
            {(labelOf ?? ((v) => v.replaceAll("_", " ")))(o.value)} ({o.count})
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Counts of each distinct value, largest first. */
export function countBy<T>(rows: T[], key: (r: T) => string) {
  const m = new Map<string, number>();
  for (const r of rows) m.set(key(r), (m.get(key(r)) ?? 0) + 1);
  return [...m.entries()].map(([value, count]) => ({ value, count })).sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
}

/** Counts where one row can carry several values (a part used by several workflows). */
export function countByMany<T>(rows: T[], keys: (r: T) => string[]) {
  const m = new Map<string, number>();
  for (const r of rows) for (const k of new Set(keys(r))) m.set(k, (m.get(k) ?? 0) + 1);
  return [...m.entries()].map(([value, count]) => ({ value, count })).sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
}

/** Workflow dropdown: every workflow that has at least one row in the list. */
export function WorkflowFilter({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; count: number }[] }) {
  return <CategoryFilter label="Filter by workflow" allLabel="All workflows" value={value} onChange={onChange} options={options} className="w-[220px] text-xs normal-case" />;
}
