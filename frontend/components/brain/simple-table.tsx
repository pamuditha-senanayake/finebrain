import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type SimpleColumn<T> = {
  id: string;
  header: string;
  cell: (row: T) => ReactNode;
  align?: "left" | "right";
  className?: string;
};

/** Plain table for review: every row fully visible, no truncation or virtualization. The header sits on its own band so it never blends into the rows. */
export function SimpleTable<T>({ rows, columns, getRowId, label, empty, onRowClick, rowClassName }: { rows: T[]; columns: SimpleColumn<T>[]; getRowId: (row: T) => string; label: string; empty?: ReactNode; onRowClick?: (row: T) => void; rowClassName?: (row: T) => string | undefined }) {
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">{empty ?? "Nothing to show."}</p>;
  return (
    <div className="overflow-x-auto rounded-xl border bg-card">
      <table className="w-full min-w-[560px] border-collapse text-[13.5px]" aria-label={label}>
        <thead className="bg-table-head">
          <tr>
            {columns.map((c) => (
              <th key={c.id} scope="col" className={cn("border-b px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.07em] text-foreground/65", c.align === "right" && "text-right", c.className)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={getRowId(r)}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={cn("border-t border-border/70 align-top transition-colors first:border-t-0 even:bg-table-stripe", onRowClick && "cursor-pointer hover:bg-table-hover", rowClassName?.(r))}
            >
              {columns.map((c) => (
                <td key={c.id} className={cn("px-4 py-3 leading-relaxed", c.align === "right" && "text-right tabular", c.className)}>
                  {c.cell(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
