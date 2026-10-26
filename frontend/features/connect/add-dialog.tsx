"use client";

// add-dialog.tsx: "Add connection". First the platform it belongs to (one already here, or a new name), then the type:
// website or app, database, connectors, or not sure. Each type opens its own path. Used by: hub.tsx.
import { Database, Globe, HelpCircle, KeyRound, type LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { Kind } from "@/lib/api/connections";
import { cn } from "@/lib/utils";

type Choice = { kind: Kind | "signin"; title: string; text: string; icon: LucideIcon };
const CHOICES: Choice[] = [
  { kind: "api", title: "Website or app", text: "Chat, orders, accounts, anything with an API", icon: Globe },
  { kind: "database", title: "Database", text: "Read only, with a user made for the brain", icon: Database },
  { kind: "signin", title: "Connectors", text: "Gmail, Slack, HubSpot and similar", icon: KeyRound },
  { kind: "other", title: "Not sure", text: "Describe it and the guide picks the way", icon: HelpCircle },
];

/** Opens the guided path for a new connection of this type on this platform. */
export function newConnectionHref(kind: Kind, platform: string, prompt = "", from = "") {
  const query = new URLSearchParams({ new: kind, ...(platform && { platform }), ...(prompt && { prompt }), ...(from && { from }) });
  return `/l2/connections?${query}`;
}

export function AddConnectionDialog({ open, onOpenChange, platforms, platform: preset }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  platforms: string[];
  platform?: string;
}) {
  const router = useRouter();
  const [platform, setPlatform] = useState(preset ?? "");
  const [signin, setSignin] = useState(false);
  const pick = (choice: Choice) => {
    if (choice.kind === "signin") return setSignin(true);
    onOpenChange(false);
    router.push(newConnectionHref(choice.kind, platform.trim()));
  };
  return (
    <Dialog open={open} onOpenChange={(next) => { onOpenChange(next); if (!next) setSignin(false); }}>
      <DialogContent className="max-w-lg space-y-6 p-6 sm:p-8">
        <div className="space-y-1.5">
          <DialogTitle className="text-lg">Add connection</DialogTitle>
          <DialogDescription className="text-[15px]">Which platform, and what kind of connection?</DialogDescription>
        </div>
        <div className="space-y-2">
          <label htmlFor="platform" className="text-[13px] font-medium text-muted-foreground">Platform</label>
          <Input id="platform" list="platforms" value={platform} onChange={(e) => setPlatform(e.target.value)} placeholder="e.g. Finebase Labs portal" className="h-10" />
          <datalist id="platforms">{platforms.map((p) => <option key={p} value={p} />)}</datalist>
        </div>
        {signin ? (
          <div className="space-y-4 rounded-lg bg-muted p-4 text-[15px] leading-relaxed">
            <p>Signing in to apps like Gmail or Slack is the next thing we build. Until then, many of them have an API the guide can connect.</p>
            <div className="flex gap-2">
              <Button onClick={() => pick(CHOICES[0])}>Use the guide</Button>
              <Button variant="ghost" onClick={() => setSignin(false)}>Back</Button>
            </div>
          </div>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {CHOICES.map((choice) => (
              <li key={choice.kind}>
                <button
                  type="button"
                  onClick={() => pick(choice)}
                  className={cn("flex h-full w-full flex-col gap-2 rounded-xl border p-4 text-left transition-colors hover:border-primary/60 hover:bg-primary/5")}
                >
                  <choice.icon className="size-5 text-muted-foreground" aria-hidden />
                  <span className="text-[15px] font-medium">{choice.title}</span>
                  <span className="text-[13px] leading-snug text-muted-foreground">{choice.text}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
