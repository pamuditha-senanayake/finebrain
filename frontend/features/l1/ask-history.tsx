"use client";

// ask-history.tsx: the Chats button and its side panel. Past chats grouped Today, Yesterday and Earlier, one line each
// (title and time); tapping one continues it. Hidden when there is no past chat.
// Used by: features/l1/ask-voice.tsx. Uses: lib/api/conversation.ts.
import { MessagesSquare } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { AskConversation } from "@/contracts";
import { useConversationList } from "@/lib/api/conversation";
import { cn } from "@/lib/utils";

type Props = { currentId: string | null; onOpen: (id: string) => void };

const DAY_MS = 24 * 60 * 60 * 1000;

/** Today, Yesterday or Earlier, by the chat's last turn. */
function groupOf(at: string): string {
  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const time = new Date(at).getTime();
  if (time >= startOfToday) return "Today";
  return time >= startOfToday - DAY_MS ? "Yesterday" : "Earlier";
}

/** A time for today and yesterday, a short date for older chats. */
function whenOf(at: string): string {
  const date = new Date(at);
  if (groupOf(at) === "Earlier") return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function grouped(chats: AskConversation[]): [string, AskConversation[]][] {
  const groups = new Map<string, AskConversation[]>();
  for (const chat of chats) groups.set(groupOf(chat.at), [...(groups.get(groupOf(chat.at)) ?? []), chat]);
  return [...groups.entries()];
}

export function AskHistory({ currentId, onOpen }: Props) {
  const [open, setOpen] = useState(false);
  // The list is read once on load for the button, and again each time the panel opens.
  const list = useConversationList(true);
  const chats = list.data ?? [];
  if (chats.length === 0) return null;

  // Step 1: continue the picked chat and close the panel
  function pick(id: string) {
    setOpen(false);
    if (id !== currentId) onOpen(id);
  }

  return (
    <>
      <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => { setOpen(true); void list.refetch(); }}>
        <MessagesSquare /> Chats
      </Button>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-full gap-0 overflow-y-auto p-0 sm:max-w-sm">
          <SheetHeader className="px-6 pt-6 pb-2">
            <SheetTitle>Chats</SheetTitle>
          </SheetHeader>
          <div className="flex flex-col gap-6 px-3 pb-8 pt-2">
            {grouped(chats).map(([group, items]) => (
              <section key={group} className="flex flex-col gap-1">
                <h2 className="px-3 text-xs font-medium text-muted-foreground">{group}</h2>
                {items.map((chat) => (
                  <button key={chat.id} type="button" onClick={() => pick(chat.id)} aria-current={chat.id === currentId}
                    className={cn("flex items-baseline gap-3 rounded-lg px-3 py-2.5 text-left text-[15px] outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/40", chat.id === currentId && "bg-muted")}>
                    <span className="min-w-0 flex-1 truncate">{chat.title}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">{whenOf(chat.at)}</span>
                  </button>
                ))}
              </section>
            ))}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
