"use client";

import {
  columnFilteringFeature,
  createColumnHelper,
  createFilteredRowModel,
  createSortedRowModel,
  filterFn_includesString,
  globalFilteringFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, ChevronsUpDown, Search } from "lucide-react";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { EmptyState } from "./primitives";

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric, basic: sortFn_basic },
  columnFilteringFeature,
  globalFilteringFeature,
  filteredRowModel: createFilteredRowModel(),
  filterFns: { includesString: filterFn_includesString },
});

export type Column<T extends object> = {
  id: string;
  header: string;
  cell: (row: T) => ReactNode;
  /** Value used for sorting and search. Defaults to an empty string (not sortable). */
  value?: (row: T) => string | number;
  width?: string;
  align?: "left" | "right";
  hideOnMobile?: boolean;
};

type Props<T extends object> = {
  data: T[];
  columns: Column<T>[];
  getRowId: (row: T) => string;
  onRowClick?: (row: T) => void;
  height?: number | string;
  searchPlaceholder?: string;
  initialSort?: { id: string; desc: boolean };
  toolbar?: ReactNode;
  rowHeight?: number;
  label: string;
  emptyText?: string;
  rowClassName?: (row: T) => string | undefined;
};

/** Dense, virtualized, sortable, searchable table. Handles tens of thousands of rows. */
export function DataTable<T extends object>({ data, columns, getRowId, onRowClick, height = 560, searchPlaceholder = "Filter…", initialSort, toolbar, rowHeight = 44, label, emptyText, rowClassName }: Props<T>) {
  const [globalFilter, setGlobalFilter] = useState("");
  const helper = useMemo(() => createColumnHelper<typeof features, T>(), []);
  const tableColumns = useMemo(
    () =>
      helper.columns(
        columns.map((c) =>
          helper.accessor((row: T) => (c.value ? c.value(row) : ""), {
            id: c.id,
            header: c.header,
            enableSorting: !!c.value,
            enableGlobalFilter: !!c.value,
            sortFn: "alphanumeric",
          }),
        ),
      ),
    [columns, helper],
  );
  const table = useTable({
    features,
    columns: tableColumns,
    data,
    getRowId: (row: T) => getRowId(row),
    globalFilterFn: "includesString",
    state: { globalFilter },
    onGlobalFilterChange: (updater: unknown) => setGlobalFilter((prev) => (typeof updater === "function" ? (updater as (p: string) => string)(prev) : (updater as string)) ?? ""),
    initialState: initialSort ? { sorting: [initialSort] } : undefined,
  });
  const rows = table.getRowModel().rows;
  const scrollRef = useRef<HTMLDivElement>(null);
  // TanStack Virtual returns functions the React Compiler cannot memoize. The component still works; it is just not auto memoized.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({ count: rows.length, getScrollElement: () => scrollRef.current, estimateSize: () => rowHeight, overscan: 12, getItemKey: (i) => rows[i].id });
  const colIndex = new Map(columns.map((c, i) => [c.id, i]));
  const template = columns.map((c) => c.width ?? "minmax(0,1fr)").join(" ");
  const mobileTemplate = columns.filter((c) => !c.hideOnMobile).map((c) => c.width ?? "minmax(0,1fr)").join(" ");

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input value={globalFilter} onChange={(e) => setGlobalFilter(e.target.value)} placeholder={searchPlaceholder} aria-label={`Filter ${label}`} className="h-9 pl-8 text-[13px]" />
        </div>
        <span className="text-xs text-muted-foreground tabular" aria-live="polite">
          {rows.length.toLocaleString()} {rows.length === 1 ? "row" : "rows"}
        </span>
        <div className="ml-auto flex items-center gap-2">{toolbar}</div>
      </div>
      <div className="overflow-hidden rounded-xl border bg-card" role="table" aria-label={label} aria-rowcount={rows.length + 1}>
        <div role="rowgroup" className="border-b bg-table-head">
          <div role="row" className="grid items-center gap-4 px-4 text-[11px] font-semibold uppercase tracking-[0.07em] text-foreground/65 max-sm:[grid-template-columns:var(--mt)] sm:[grid-template-columns:var(--t)]" style={{ "--t": template, "--mt": mobileTemplate } as React.CSSProperties}>
            {table.getHeaderGroups()[0].headers.map((header) => {
              const col = columns[colIndex.get(header.column.id) ?? 0];
              const sorted = header.column.getIsSorted();
              const canSort = header.column.getCanSort();
              return (
                <div role="columnheader" key={header.id} aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"} className={cn("whitespace-nowrap py-2.5", col.align === "right" && "text-right", col.hideOnMobile && "max-sm:hidden")}>
                  {canSort ? (
                    <button type="button" onClick={header.column.getToggleSortingHandler()} className={cn("inline-flex items-center gap-1 rounded uppercase tracking-[0.07em] hover:text-foreground", col.align === "right" && "flex-row-reverse")}>
                      {col.header}
                      {sorted === "asc" ? <ArrowUp className="size-3" /> : sorted === "desc" ? <ArrowDown className="size-3" /> : <ChevronsUpDown className="size-3 opacity-40" />}
                    </button>
                  ) : (
                    col.header
                  )}
                </div>
              );
            })}
          </div>
        </div>
        {rows.length === 0 ? (
          <div className="p-4">
            <EmptyState title={emptyText ?? "No rows match"} />
          </div>
        ) : (
          <div ref={scrollRef} role="rowgroup" tabIndex={0} aria-label={`${label} rows, scrollable`} className="scrollbar-thin overflow-auto" style={{ height: rows.length * rowHeight + 2, maxHeight: height }}>
            <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
              {virtualizer.getVirtualItems().map((item) => {
                const row = rows[item.index];
                const original = row.original as T;
                return (
                  <div
                    key={row.id}
                    role="row"
                    aria-rowindex={item.index + 2}
                    data-index={item.index}
                    tabIndex={onRowClick ? 0 : undefined}
                    onClick={onRowClick ? () => onRowClick(original) : undefined}
                    onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(original) : undefined}
                    className={cn(
                      "absolute left-0 top-0 grid w-full items-center gap-4 border-b border-border/70 px-4 text-[13.5px] transition-colors last:border-b-0 max-sm:[grid-template-columns:var(--mt)] sm:[grid-template-columns:var(--t)]",
                      item.index % 2 === 1 && "bg-table-stripe",
                      onRowClick && "cursor-pointer hover:bg-table-hover focus-visible:bg-table-hover",
                      rowClassName?.(original),
                    )}
                    style={{ height: rowHeight, transform: `translateY(${item.start}px)`, "--t": template, "--mt": mobileTemplate } as React.CSSProperties}
                  >
                    {columns.map((c) => (
                      <div role="cell" key={c.id} className={cn("min-w-0 truncate", c.align === "right" && "text-right tabular", c.hideOnMobile && "max-sm:hidden")}>
                        {c.cell(original)}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
