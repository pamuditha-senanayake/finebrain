"use client";

// intake-card.tsx: the part of Lisena's reply you can click while adding a document in the chat. Everything here can
// also be typed or said: a choice is its words, Add is "yes", Stop is "cancel", and any detail is "change the X to Y".
// Used by: ask-chat.tsx, components/shell/ask-bubble.tsx. Uses: lib/voice/agent.ts, lib/voice/intake-chat.ts.
import { Check, FileUp, ListTodo, Paperclip } from "lucide-react";
import Link from "next/link";
import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { UPLOAD_TYPES } from "@/lib/api/upload";
import { attach, send } from "@/lib/voice/agent";
import type { IntakeCard as Card } from "@/lib/voice/intake-chat";

/** Only the newest reply is live; older ones keep their words and lose their buttons. */
export function IntakeCard({ card }: { card: Card }) {
  const reply = (words: string) => void send(words, { speak: true });
  if (card.kind === "attach") return <ChooseFile />;
  if (card.kind === "question") return null;
  if (card.kind === "choices")
    return (
      <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Choose one">
        {card.options.map((label) => (
          <Button key={label} variant="outline" size="sm" className="rounded-full" onClick={() => reply(label)}>{label}</Button>
        ))}
      </div>
    );
  if (card.kind === "review")
    return (
      <div className="mt-3 space-y-3">
        <dl className="divide-y rounded-2xl border bg-surface text-sm">
          {card.rows.map(([label, value]) => (
            <div key={label} className="flex gap-3 px-3 py-2">
              <dt className="w-28 shrink-0 text-muted-foreground">{label}</dt>
              <dd className="min-w-0 flex-1 break-words">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-muted-foreground">To fix something, say or type it, like “change the owner to Nimal”.</p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" className="rounded-full" onClick={() => reply("yes")}><Check /> Add to knowledge base</Button>
          <Button size="sm" variant="ghost" className="rounded-full text-muted-foreground" onClick={() => reply("cancel")}>Stop</Button>
        </div>
      </div>
    );
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <Button asChild size="sm" variant="outline" className="rounded-full"><Link href={`/l2/library?doc=${card.documentId}`}><FileUp /> Open in Library</Link></Button>
      {card.tasks > 0 && <Button asChild size="sm" variant="outline" className="rounded-full"><Link href="/l1/tasks"><ListTodo /> See {card.tasks === 1 ? "the task" : `${card.tasks} tasks`}</Link></Button>}
    </div>
  );
}

function ChooseFile() {
  const picker = useRef<HTMLInputElement>(null);
  return (
    <div className="mt-3">
      <input ref={picker} type="file" accept={UPLOAD_TYPES} className="hidden" aria-label="File to add" onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; if (file) void attach(file); }} />
      <Button size="sm" className="rounded-full" onClick={() => picker.current?.click()}><Paperclip /> Choose a file</Button>
      <p className="mt-2 text-xs text-muted-foreground">Text, Markdown, CSV, PDF or Word, up to 10 MB.</p>
    </div>
  );
}
