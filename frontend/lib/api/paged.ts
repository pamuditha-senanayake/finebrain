"use client";

// Lists of thousands (step 12). The server filters, searches, sorts and pages; this hook asks for only the pages a table
// is showing and keeps them. `q` finds rows without hiding the rest; filters narrow the list; `around` lands on a row.
import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import type { z } from "zod";
import { ListPage } from "@/contracts";
import { useUi } from "@/lib/store";
import { apiGet } from "./client";

export const PAGE = 100;
const TYPING_MS = 250;
const SETTLE_MS = 90; // while the scrollbar is dragged fast, pages are asked for only once it slows down

export type Paged<T> = {
  q: string;
  setQ: (q: string) => void;
  filters: Record<string, string>;
  setFilter: (field: string, value: string | null) => void;
  clearFilters: () => void;
  sort: string;
  setSort: (sort: string) => void;
  total: number;
  rowAt: (index: number) => T | undefined;
  facets: Record<string, Record<string, number>>;
  matches: number[];
  position: number | null;
  ready: boolean;
  error: unknown;
  setRange: (first: number, last: number) => void;
};

function query(params: Record<string, string>) {
  return new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "")).toString();
}

export function usePagedList<S extends z.ZodTypeAny>(name: string, item: S, opts: { around?: string; filters?: Record<string, string>; sort?: string } = {}): Paged<z.infer<S>> {
  const tenantId = useUi((s) => s.tenantId);
  const [q, setQ] = useState("");
  const [typed, setTyped] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>(opts.filters ?? {});
  const [sort, setSort] = useState(opts.sort ?? "");
  const [range, setRange] = useState<[number, number]>([0, 0]);
  const settle = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(settle.current), []);
  useEffect(() => {
    const t = setTimeout(() => setTyped(q.trim()), TYPING_MS);
    return () => clearTimeout(t);
  }, [q]);

  const base = useMemo(() => ({ ...filters, q: typed, sort, limit: String(PAGE) }), [filters, typed, sort]);
  const key = JSON.stringify(base);
  const schema = useMemo(() => ListPage(item), [item]);
  // The first call carries what is the same on every page, and lands on the target row when there is one.
  const first = useQuery({
    queryKey: ["t", tenantId, name, "lists", key, "first", opts.around ?? ""],
    queryFn: ({ signal }) => apiGet(`lists/${name}?${query({ ...base, ...(opts.around ? { around: opts.around } : {}) })}`, schema, signal),
    placeholderData: keepPreviousData,
  });
  const head = first.data;
  const wanted = useMemo(() => {
    const pages = new Set<number>();
    for (let p = Math.floor(range[0] / PAGE); p <= Math.floor(range[1] / PAGE); p++) pages.add(p);
    const landed = head ? head.offset / PAGE : 0;
    return [...pages].filter((p) => p !== landed);
  }, [range, head]);
  const more = useQueries({
    queries: wanted.map((p) => ({
      queryKey: ["t", tenantId, name, "lists", key, "page", p],
      queryFn: ({ signal }: { signal: AbortSignal }) => apiGet(`lists/${name}?${query({ ...base, offset: String(p * PAGE) })}`, schema, signal),
      placeholderData: keepPreviousData,
    })),
  });
  const pages = new Map<number, z.infer<S>[]>();
  if (head) pages.set(head.offset / PAGE, head.items);
  more.forEach((r, i) => r.data && pages.set(wanted[i], r.data.items));

  return {
    q,
    setQ,
    filters,
    setFilter: (field, value) => setFilters((f) => (value === null || value === "" ? Object.fromEntries(Object.entries(f).filter(([k]) => k !== field)) : { ...f, [field]: value })),
    clearFilters: () => setFilters({}),
    sort,
    setSort,
    total: head?.total ?? 0,
    rowAt: (index) => pages.get(Math.floor(index / PAGE))?.[index % PAGE],
    facets: head?.facets ?? {},
    matches: head?.matches.positions ?? [],
    position: head?.position ?? null,
    ready: !!head,
    error: first.error,
    setRange: (a, b) => {
      clearTimeout(settle.current);
      settle.current = setTimeout(() => setRange((r) => (r[0] === a && r[1] === b ? r : [a, b])), SETTLE_MS);
    },
  };
}
