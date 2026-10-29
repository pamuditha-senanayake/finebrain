"use client";

// voice-settings.tsx: how Lisena listens and answers, in one small popover: hands-free, edit before sending, spoken
// replies, and the key that talks from any page. Used by: ask-bubble.tsx, features/l1/ask-voice.tsx. Uses: lib/voice/agent.ts.
import { SlidersHorizontal } from "lucide-react";
import { useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { useVoiceSettings } from "@/lib/voice/agent";

const noop = () => () => {};
/** "⌥ Option" on a Mac, "Alt" elsewhere; the server renders Alt, then the browser corrects it. */
export const useTalkKey = () => useSyncExternalStore(noop, () => (/Mac|iPhone|iPad/.test(navigator.platform) ? "⌥ Option" : "Alt"), () => "Alt");

const ROWS = [
  { key: "handsFree", label: "Hands-free", hint: "Listens again after each reply." },
  { key: "editFirst", label: "Edit before sending", hint: "What you say goes in the box first." },
  { key: "speakOut", label: "Spoken replies", hint: "Reads each answer aloud." },
] as const;

export function VoiceSettings({ className }: { className?: string }) {
  const settings = useVoiceSettings();
  const talkKey = useTalkKey();
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon-sm" className={className ?? "text-muted-foreground"} aria-label="Voice settings" title="Voice settings">
          <SlidersHorizontal />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-4" data-ask-ignore>
        <p className="text-sm font-semibold">Voice</p>
        <ul className="mt-3 space-y-4">
          {ROWS.map((row) => (
            <li key={row.key} className="flex items-start justify-between gap-4">
              <label htmlFor={`voice-${row.key}`} className="cursor-pointer">
                <span className="block text-[15px]">{row.label}</span>
                <span className="block text-xs text-muted-foreground">{row.hint}</span>
              </label>
              <Switch id={`voice-${row.key}`} className="mt-1" checked={settings[row.key]} onCheckedChange={(on) => settings.change({ [row.key]: on })} />
            </li>
          ))}
        </ul>
        <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">
          Hold <kbd className="rounded border bg-surface px-1 font-mono">{talkKey}</kbd> to talk on any page. Let go to send.
        </p>
      </PopoverContent>
    </Popover>
  );
}
