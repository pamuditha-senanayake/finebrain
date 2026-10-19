"use client";

// Focus links (step 11). Any page can be opened with ?focus=kind:id, and with &span=start:end and &q=words when the
// thing to find is a sentence inside it. A page only marks its rows and cards with data-focus-id="kind:id"; the shared
// runner (components/shell/focus-runner.tsx) scrolls to it and lights it up. Pages with lists read the target too, to
// scroll a virtual list to the row first.
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";

export type FocusTarget = { kind: string; id: string; span: [number, number] | null; words: string[]; key: string };

export function parseFocus(params: URLSearchParams): FocusTarget | null {
  const raw = params.get("focus");
  const at = raw ? raw.indexOf(":") : -1;
  if (!raw || at < 1) return null;
  const [start, end] = (params.get("span") ?? "").split(":").map(Number);
  const span: [number, number] | null = Number.isInteger(start) && Number.isInteger(end) && end > start ? [start, end] : null;
  const words = (params.get("q") ?? "").toLowerCase().split(/\s+/).filter((w) => w.length > 1);
  return { kind: raw.slice(0, at), id: raw.slice(at + 1), span, words, key: params.toString() };
}

/** The focus in the address bar, or null. */
export function useFocusTarget(): FocusTarget | null {
  const params = useSearchParams();
  return useMemo(() => parseFocus(new URLSearchParams(params.toString())), [params]);
}

/** The attribute value a row or card carries, so the runner can find it. */
export const focusId = (kind: string, id: string) => `${kind}:${id}`;

/** A link that opens a page with something lit up. */
export function focusHref(path: string, kind: string, id: string, extra: Record<string, string> = {}) {
  return `${path}?${new URLSearchParams({ ...extra, focus: focusId(kind, id) }).toString()}`;
}
