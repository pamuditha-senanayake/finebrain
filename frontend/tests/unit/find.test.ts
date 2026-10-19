// Steps 11 and 12 on the client: focus links parse into a target, and the mock list pages behave like the server's.
import { describe, expect, it } from "vitest";
import { focusHref, parseFocus } from "@/lib/focus";
import { listPage } from "@/lib/mock/lists";
import { buildFinebase } from "@/lib/mock/seed/build";
import { search } from "@/lib/mock/queries";

const urlOf = (query: string) => new URL(`http://x/api/t/t/lists/runs?${query}`);

describe("focus links", () => {
  it("reads kind, id, span and words", () => {
    const target = parseFocus(new URLSearchParams("focus=chunk:doc_1_c2&span=15:77&q=Saturday%20hours"));
    expect(target).toMatchObject({ kind: "chunk", id: "doc_1_c2", span: [15, 77], words: ["saturday", "hours"] });
  });

  it("keeps a colon inside the id, and ignores a missing or broken focus", () => {
    expect(parseFocus(new URLSearchParams("focus=run:a:b"))).toMatchObject({ kind: "run", id: "a:b", span: null });
    expect(parseFocus(new URLSearchParams(""))).toBeNull();
    expect(parseFocus(new URLSearchParams("focus=nokind"))).toBeNull();
    expect(parseFocus(new URLSearchParams("focus=run:x&span=9:3"))?.span).toBeNull();
  });

  it("builds a link that parses back", () => {
    const href = focusHref("/l3/runs", "run", "run_7");
    expect(parseFocus(new URLSearchParams(href.split("?")[1]))).toMatchObject({ kind: "run", id: "run_7" });
  });
});

describe("mock list pages", () => {
  const d = buildFinebase();

  it("page, count and facet each value against the other filters", () => {
    const first = listPage(d, "runs", urlOf("limit=25"))!;
    expect(first.items).toHaveLength(25);
    expect(first.total).toBe(d.runs.length);
    const status = d.runs[0].status;
    const filtered = listPage(d, "runs", urlOf(`status=${status}`))!;
    expect(filtered.total).toBe(d.runs.filter((r) => r.status === status).length);
    expect(Object.values(filtered.facets.agentId).reduce((a, b) => a + b, 0)).toBe(filtered.total);
  });

  it("search finds without hiding, and around lands on the page with the row", () => {
    const row = listPage(d, "runs", urlOf("limit=1&offset=57"))!.items[0];
    const found = listPage(d, "runs", urlOf(`q=${encodeURIComponent(row.id)}&limit=10`))!;
    expect(found.total).toBe(d.runs.length);
    expect(found.matches.positions).toEqual([57]);
    const landed = listPage(d, "runs", urlOf(`around=${row.id}&limit=10`))!;
    expect(landed.position).toBe(57);
    expect(landed.offset).toBe(50);
    expect(landed.items.some((r) => r.id === row.id)).toBe(true);
  });

  it("answers null for a list it does not serve", () => {
    expect(listPage(d, "nothing", urlOf(""))).toBeNull();
  });
});

describe("mock search", () => {
  it("returns a focus for runs, so the palette can light the row", () => {
    const d = buildFinebase();
    const hit = search(d, d.runs[3].id).find((h) => h.kind === "Run");
    expect(hit?.focus).toEqual({ kind: "run", id: d.runs[3].id });
    expect(hit?.href).toContain(`focus=run:${d.runs[3].id}`);
  });
});
