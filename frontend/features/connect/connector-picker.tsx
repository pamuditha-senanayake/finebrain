"use client";

import { ChevronLeft, Search } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { CATEGORY, CONNECTORS, METHOD, type Category, type Connector } from "@/lib/connect/catalog";
import { ConnectForm, ConnectorMark } from "./connect-form";

/** A tool that is not in the list, named by what the person searched for. */
export const otherTool = (name: string): Connector => ({ id: "other", name: name.trim() || "Other tool", category: "other", method: "mcp" });

/** Pick a system, then connect it, in one dialog. Search narrows the list; "Not listed" covers everything else. */
export function ConnectorPicker({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<Connector | null>(null);

  function close(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setPicked(null);
      setQ("");
    }
  }

  const hits = CONNECTORS.filter((c) => c.name.toLowerCase().includes(q.trim().toLowerCase()));
  const groups = (Object.keys(CATEGORY) as Category[]).map((cat) => [cat, hits.filter((c) => c.category === cat)] as const).filter(([, list]) => list.length);

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="gap-0 p-0 sm:max-w-xl">
        {picked ? (
          <div className="p-6 sm:p-8">
            <Button variant="ghost" size="sm" className="-ml-2 mb-4 text-muted-foreground" onClick={() => setPicked(null)}><ChevronLeft /> All</Button>
            <div className="mb-6 flex items-center gap-4">
              <ConnectorMark connector={picked} />
              <div>
                <DialogTitle className="text-lg font-semibold">{picked.name}</DialogTitle>
                <p className="mt-1 text-sm text-muted-foreground">{picked.id === "other" ? "How can we reach it?" : METHOD[picked.method].label}</p>
              </div>
            </div>
            <ConnectForm connector={picked} onDone={() => { toast.success(`${picked.name} added to sensors`); close(false); }} />
          </div>
        ) : (
          <>
            <div className="border-b p-6 pb-5">
              <DialogTitle className="text-lg font-semibold">Add a connector</DialogTitle>
              <label className="mt-4 flex h-11 items-center gap-3 rounded-xl border bg-background px-4 focus-within:ring-3 focus-within:ring-ring/40">
                <Search className="size-4 text-muted-foreground" aria-hidden />
                <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Gmail, Slack, Postgres…" aria-label="Search connectors" className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground" />
              </label>
            </div>
            <div className="max-h-[60dvh] space-y-6 overflow-y-auto p-6">
              {groups.map(([cat, list]) => (
                <section key={cat}>
                  <h3 className="mb-2 text-xs font-medium uppercase tracking-[0.07em] text-muted-foreground">{CATEGORY[cat].label}</h3>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {list.map((c) => (
                      <button key={c.id} type="button" onClick={() => setPicked(c)} className="flex items-center gap-3 rounded-xl border bg-surface p-3 text-left text-[15px] transition-colors hover:border-primary/40">
                        <ConnectorMark connector={c} className="size-8 rounded-lg" />
                        <span className="truncate">{c.name}</span>
                      </button>
                    ))}
                  </div>
                </section>
              ))}
              <button type="button" onClick={() => setPicked(otherTool(q))} className="flex w-full items-center justify-between rounded-xl border border-dashed px-5 py-4 text-left transition-colors hover:border-primary/40">
                <span className="text-[15px] font-medium">{q.trim() && !hits.length ? `Add “${q.trim()}”` : "Not listed?"}</span>
                <span className="text-sm text-muted-foreground">MCP, webhook or files</span>
              </button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
