"use client";

// PagedTable (step 12): a virtual table over a list the server pages. The scrollbar spans every row; only the pages on
// screen are fetched. Search finds without hiding, and the stepper jumps between matches; a target row is scrolled to
// and shown with the focus effect (step 11). Used by runs.tsx. Uses: lib/api/paged.ts, lib/focus-fx.ts.
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, ChevronsUpDown, Search } from "lucide-react";
import { memo, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Input } from "@/components/ui/input";
import type { Paged } from "@/lib/api/paged";
import { showMe } from "@/lib/focus-fx";
import { cn } from "@/lib/utils";
import { MatchStepper } from "./match-stepper";
import { EmptyState } from "./primitives";

export type PagedColumn<T> = { id: string; header: string; cell: (row: T) => ReactNode; sortKey?: string; width?: string; align?: "left" | "right"; hideOnMobile?: boolean };

type Props<T extends { id: string }> = {
  list: Paged<T>;
  columns: PagedColumn<T>[];
  label: string;
  focusKind: string;
  /** A row id to land on, from a focus link. */
  focusId?: string | null;
  onRowClick?: (row: T) => void;
  rowClassName?: (row: T) => string | undefined;
  toolbar?: ReactNode;
  below?: ReactNode;
  searchPlaceholder?: string;
  height?: number | string;
  rowHeight?: number;
};

export function PagedTable<T extends { id: string }>({ list, columns, label, focusKind, focusId, onRowClick, rowClassName, toolbar, below, searchPlaceholder = "Search", height = 560, rowHeight = 44 }: Props<T>) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(0);
  const [stepping, setStepping] = useState<number | null>(null);
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({ count: list.total, getScrollElement: () => scrollRef.current, estimateSize: () => rowHeight, overscan: 6 });
  const items = virtualizer.getVirtualItems();
  const first = items[0]?.index ?? 0;
  const last = items.at(-1)?.index ?? 0;
  useEffect(() => list.setRange(first, last), [first, last]); // eslint-disable-line react-hooks/exhaustive-deps
  const matchSet = useMemo(() => new Set(list.matches), [list.matches]);
  const template = columns.map((c) => c.width ?? "minmax(0,1fr)").join(" ");
  const mobileTemplate = columns.filter((c) => !c.hideOnMobile).map((c) => c.width ?? "minmax(0,1fr)").join(" ");
  const gridStyle = useMemo(() => ({ "--t": template, "--mt": mobileTemplate }) as CSSProperties, [template, mobileTemplate]);
  const searched = list.q.trim().length > 0;

  // A focus link lands on its row: scroll the virtual list there, then the shared runner lights the row.
  const landed = useRef<string | null>(null);
  useEffect(() => {
    const here = `${focusId}:${list.position}`; // the position of the new target arrives after the id does
    if (focusId && list.position !== null && landed.current !== here) {
      landed.current = here;
      virtualizer.scrollToIndex(list.position, { align: "center" });
    }
  }, [focusId, list.position]); // eslint-disable-line react-hooks/exhaustive-deps

  // Stepping to a match: scroll there, and once that page has arrived show the row. A new search lands on its first match.
  const goTo = (next: number) => {
    setStep(next);
    setStepping(list.matches[next] ?? null);
    if (list.matches[next] !== undefined) virtualizer.scrollToIndex(list.matches[next], { align: "center" });
  };
  const steppedRow = stepping === null ? undefined : list.rowAt(stepping);
  useEffect(() => (steppedRow ? showMe({ kind: focusKind, id: steppedRow.id, span: null, words: [], key: "" }) : undefined), [steppedRow?.id, focusKind]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (list.q.trim() && list.matches.length) goTo(0);
  }, [list.matches]); // eslint-disable-line react-hooks/exhaustive-deps

  const sorted = list.sort.split(":");
  const toggleSort = (key: string) => list.setSort(sorted[0] !== key ? `${key}:desc` : sorted[1] === "desc" ? `${key}:asc` : "");

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input value={list.q} onChange={(e) => list.setQ(e.target.value)} placeholder={searchPlaceholder} aria-label={`Search ${label}`} className="h-9 pl-8 text-[13px]" />
        </div>
        <MatchStepper searched={searched && list.ready} count={list.matches.length} index={step} onStep={goTo} />
        {list.ready && <span className="text-xs text-muted-foreground tabular" aria-live="polite">{list.total.toLocaleString()} {list.total === 1 ? "row" : "rows"}</span>}
        <div className="ml-auto flex items-center gap-2">{toolbar}</div>
      </div>
      {below}
      <div className="overflow-hidden rounded-xl border bg-card" role="table" aria-label={label} aria-rowcount={list.total + 1}>
        <div role="rowgroup" className="border-b bg-table-head">
          <div role="row" className="grid items-center gap-4 px-4 text-[11px] font-semibold uppercase tracking-[0.07em] text-foreground/65 max-sm:[grid-template-columns:var(--mt)] sm:[grid-template-columns:var(--t)]" style={gridStyle}>
            {columns.map((c) => {
              const on = c.sortKey && sorted[0] === c.sortKey ? sorted[1] : null;
              return (
                <div role="columnheader" key={c.id} aria-sort={on === "asc" ? "ascending" : on === "desc" ? "descending" : "none"} className={cn("whitespace-nowrap py-2.5", c.align === "right" && "text-right", c.hideOnMobile && "max-sm:hidden")}>
                  {c.sortKey ? (
                    <button type="button" onClick={() => toggleSort(c.sortKey!)} className={cn("inline-flex items-center gap-1 rounded uppercase tracking-[0.07em] hover:text-foreground", c.align === "right" && "flex-row-reverse")}>
                      {c.header}
                      {on === "asc" ? <ArrowUp className="size-3" /> : on === "desc" ? <ArrowDown className="size-3" /> : <ChevronsUpDown className="size-3 opacity-40" />}
                    </button>
                  ) : c.header}
                </div>
              );
            })}
          </div>
        </div>
        {list.ready && list.total === 0 ? (
          <div className="p-4"><EmptyState title="No rows match" /></div>
        ) : (
          <div ref={scrollRef} role="rowgroup" tabIndex={0} aria-label={`${label} rows, scrollable`} className="scrollbar-thin overflow-auto" style={{ height: Math.max(list.total, 3) * rowHeight + 2, maxHeight: height }}>
            <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
              {items.map((item) => {
                const row = list.rowAt(item.index);
                return (
                  <PagedRow key={item.index} row={row} index={item.index} start={item.start} height={rowHeight} columns={columns} focusKind={focusKind} matched={matchSet.has(item.index)}
                    extra={row ? rowClassName?.(row) : undefined} onRowClick={onRowClick} gridStyle={gridStyle} />
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

type RowProps<T extends { id: string }> = {
  row: T | undefined;
  index: number;
  start: number;
  height: number;
  columns: PagedColumn<T>[];
  focusKind: string;
  matched: boolean;
  extra: string | undefined;
  onRowClick?: (row: T) => void;
  gridStyle: CSSProperties;
};

/** One row. Memoised: scrolling re-renders the table every frame, but a row whose data and place did not change is left alone. */
const PagedRow = memo(function PagedRow<T extends { id: string }>({ row, index, start, height, columns, focusKind, matched, extra, onRowClick, gridStyle }: RowProps<T>) {
  if (!row) {
    // A row still on its way: one bar, not a cell per column, so a fast scroll stays cheap.
    return (
      <div role="row" aria-rowindex={index + 2} data-index={index} className={cn("absolute left-0 top-0 flex w-full items-center border-b border-border/70 px-4", index % 2 === 1 && "bg-table-stripe")} style={{ height, transform: `translateY(${start}px)` }}>
        <span className="inline-block h-3 w-1/2 animate-pulse rounded bg-muted" aria-hidden />
      </div>
    );
  }
  return (
    <div role="row" aria-rowindex={index + 2} data-index={index} data-focus-id={`${focusKind}:${row.id}`} data-match={matched ? "true" : undefined}
      tabIndex={onRowClick ? 0 : undefined} onClick={onRowClick ? () => onRowClick(row) : undefined} onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(row) : undefined}
      className={cn("absolute left-0 top-0 grid w-full items-center gap-4 border-b border-border/70 px-4 text-[13.5px] transition-colors max-sm:[grid-template-columns:var(--mt)] sm:[grid-template-columns:var(--t)]",
        index % 2 === 1 && "bg-table-stripe", onRowClick && "cursor-pointer hover:bg-table-hover focus-visible:bg-table-hover", extra)}
      style={{ ...gridStyle, height, transform: `translateY(${start}px)` }}>
      {columns.map((c) => (
        <div role="cell" key={c.id} className={cn("min-w-0 truncate", c.align === "right" && "text-right tabular", c.hideOnMobile && "max-sm:hidden")}>
          {c.cell(row)}
        </div>
      ))}
    </div>
  );
}) as <T extends { id: string }>(props: RowProps<T>) => ReactNode;
