"use client";

// ask-hint.tsx: a quiet label beside the floating blob: what it is for and its keyboard shortcut. No highlight, and it
// goes away while the bubble is open or on small screens. Used by: ask-orb.tsx.
import { useSyncExternalStore } from "react";

const nothing = () => () => {};
const onThisDevice = () => (/Mac|iPhone|iPad/.test(navigator.platform) ? "⌘J" : "Ctrl J");
const onTheServer = () => "Ctrl J"; // the server cannot know the device, so the first paint says Ctrl J

export function AskHint() {
  const shortcut = useSyncExternalStore(nothing, onThisDevice, onTheServer);
  return (
    <p className="pointer-events-none fixed bottom-9 right-24 z-30 hidden text-[13px] text-muted-foreground sm:block" aria-hidden>
      Ask anything · <kbd className="font-sans">{shortcut}</kbd>
    </p>
  );
}
