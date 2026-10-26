"use client";

// desk-guide.tsx: the guide chat beside the step card. It opens with a question fitting the chosen type, works on one
// connection at a time, drafts it when it has enough, and the request is ready to copy right in the chat. Used by: desk.tsx. Uses: lib/api/connections.ts.
import { useQueryClient } from "@tanstack/react-query";
import { Copy, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiGet } from "@/lib/api/client";
import { type Connection, type Kind, type Turn, askGuide } from "@/lib/api/connections";
import { useTenantId } from "@/lib/api/hooks";
import { z } from "zod";

type Shown = Turn & { briefFor?: string };
/** Chats kept while the page is open, by connection, so a chat survives the move to the connection it just created. */
const kept = new Map<string, Shown[]>();

const OPENING: Record<Kind, string> = {
  api: "Which website or app is it, and what should the brain do with it?",
  database: "Which database is it, and what should the brain read from it? It will only ever read.",
  other: "What do you want to connect, and what should the brain do with it?",
};

function opening(connection: Connection | null, kind: Kind): string {
  if (!connection) return OPENING[kind];
  return `Ask me anything about connecting ${connection.system || connection.name}.`;
}

async function copyBrief(connectionId: string) {
  const { brief } = await apiGet(`connections/${connectionId}/brief`, z.object({ brief: z.string() }));
  await navigator.clipboard.writeText(brief);
  toast.success("Copied. Send it to whoever builds this system.");
}

export function GuideChat({ connection, start, onDrafted }: {
  connection: Connection | null;
  start?: { kind: Kind; platform: string; prompt: string; from?: string };
  onDrafted: (id: string) => void;
}) {
  const kind = start?.kind ?? "other";
  const [turns, setTurns] = useState<Shown[]>(() => (connection && kept.get(connection.id)) || [{ role: "assistant", text: opening(connection, kind) }]);
  const [draft, setDraft] = useState(start?.prompt ?? "");
  const [thinking, setThinking] = useState(false);
  const queryClient = useQueryClient();
  const tenantId = useTenantId();
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [turns, thinking]);

  const send = async () => {
    const opened = turns.length === 1 ? [{ role: "assistant" as const, text: opening(connection, kind) }] : turns; // freeze the opening line as shown
    const asked: Shown[] = [...opened, { role: "user", text: draft.trim() }];
    setTurns(asked);
    setDraft("");
    setThinking(true);
    try {
      const plain = asked.map(({ role, text }) => ({ role, text }));
      const { answer, connection: drafted } = await askGuide(connection?.id ?? null, plain, connection ? undefined : { kind, platform: start?.platform ?? "", fromConnection: start?.from, fromItem: start?.prompt });
      const changed = drafted && JSON.stringify(drafted.needs) !== JSON.stringify(connection?.needs);
      const after: Shown[] = [...asked, { role: "assistant", text: answer, briefFor: changed ? drafted.id : undefined }];
      setTurns(after);
      const id = drafted?.id ?? connection?.id;
      if (id) kept.set(id, after);
      await queryClient.invalidateQueries({ queryKey: ["t", tenantId, "connections"] });
      if (drafted && drafted.id !== connection?.id) onDrafted(drafted.id);
    } catch {
      setTurns([...asked, { role: "assistant", text: "I can't answer right now. Please try again in a moment." }]);
    } finally {
      setThinking(false);
    }
  };

  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-xl border bg-card p-5 lg:sticky lg:top-4" aria-label="Guide">
      <h2 className="text-[15px] font-semibold">Guide</h2>
      <div ref={list} className="flex max-h-[55dvh] flex-col gap-3 overflow-y-auto overflow-x-hidden break-words" aria-live="polite">
        {turns.map((turn, i) => (i === 0 && turns.length === 1 ? { ...turn, text: opening(connection, kind) } : turn)).map((turn, i) => (
          <div key={i} className={turn.role === "user" ? "self-end rounded-2xl bg-primary/10 px-3.5 py-2.5 text-[15px]" : "space-y-2.5"}>
            <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{turn.text}</p>
            {turn.briefFor && (
              <Button size="sm" variant="outline" onClick={() => copyBrief(turn.briefFor!)}><Copy /> Copy request</Button>
            )}
          </div>
        ))}
        {thinking && <p className="text-[13px] text-muted-foreground">Thinking</p>}
      </div>
      <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (draft.trim() && !thinking) void send(); }}>
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (draft.trim() && !thinking) void send(); } }}
          placeholder="Your answer"
          aria-label="Message to the guide"
          className="min-h-11 text-[15px]"
          rows={2}
        />
        <Button type="submit" size="icon" disabled={!draft.trim() || thinking} aria-label="Send"><Send /></Button>
      </form>
    </section>
  );
}
