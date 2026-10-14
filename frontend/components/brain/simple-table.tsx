import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type SimpleColumn<T> = {
  id: string;
  header: string;
  cell: (row: T) => ReactNode;
  align?: "left" | "right";
  className?: string;
};

/** Plain bordered table for review: every row fully visible, no truncation or virtualization. */
export function SimpleTable<T>({ rows, columns, getRowId, label, empty, onRowClick, rowClassName }: { rows: T[]; columns: SimpleColumn<T>[]; getRowId: (row: T) => string; label: string; empty?: ReactNode; onRowClick?: (row: T) => void; rowClassName?: (row: T) => string | undefined }) {
  if (rows.length === 0) return <p className="text-xs text-muted-foreground">{empty ?? "Nothing to show."}</p>;
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[560px] text-[13px]" aria-label={label}>
        <thead className="bg-surface text-[11px] uppercase tracking-wide text-muted-foreground">
          <tr>
            {columns.map((c) => (
              <th key={c.id} scope="col" className={cn("px-3 py-2 text-left font-semibold", c.align === "right" && "text-right", c.className)}>
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
              className={cn("border-t align-top", onRowClick && "cursor-pointer hover:bg-accent/60", rowClassName?.(r))}
            >
              {columns.map((c) => (
                <td key={c.id} className={cn("px-3 py-2", c.align === "right" && "text-right tabular", c.className)}>
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
