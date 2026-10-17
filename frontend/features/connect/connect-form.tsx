"use client";

import { Check, Copy, Loader2, Upload } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { CATEGORY, DB_PLACEHOLDER, FALLBACKS, METHOD, listenOf, type Connector, type Method } from "@/lib/connect/catalog";
import { useConnect } from "@/lib/connect/store";
import { cn } from "@/lib/utils";

const field = "h-11 w-full rounded-xl border bg-background px-4 text-[15px] outline-none placeholder:text-muted-foreground focus-visible:ring-3 focus-visible:ring-ring/40";

/**
 * Connects one system. Each method asks for the one thing it needs and nothing else.
 * Nothing leaves the browser yet: signing in is simulated until the backend has real OAuth.
 */
export function ConnectForm({ connector, onDone }: { connector: Connector; onDone: () => void }) {
  const connect = useConnect((s) => s.connect);
  const [method, setMethod] = useState<Method | "request" | null>(connector.id === "other" ? null : connector.method);
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const hook = `https://hooks.companybrain.app/in/${connector.id}-${Math.abs(hashOf(connector.name)).toString(36)}`;

  function finish(detail: string, m: Method | "request" = method ?? connector.method) {
    connect({ connectorId: connector.id, name: connector.name, method: m, detail });
    onDone();
  }

  // Signing in waits a moment, like the real consent screen would.
  function signIn() {
    const what = value.split(",").map((x) => x.trim()).filter(Boolean).join(", ");
    if (!what) return;
    setBusy(true);
    setTimeout(() => finish(what), 1100);
  }

  // A tool that is not in the list: first choose how the brain can reach it.
  if (!method) {
    return (
      <div className="space-y-2">
        {FALLBACKS.map((f) => (
          <button key={f.id} type="button" onClick={() => (f.id === "request" ? finish("We will build it", "request") : setMethod(f.id))} className="flex w-full items-center justify-between gap-4 rounded-xl border bg-surface px-5 py-4 text-left transition-colors hover:border-primary/40">
            <span className="text-[15px] font-medium">{f.label}</span>
            <span className="text-sm text-muted-foreground">{f.hint}</span>
          </button>
        ))}
      </div>
    );
  }

  // Sign in, after saying what to listen to: the inboxes, channels or repos the brain should read.
  if (method === "oauth") {
    const listen = listenOf(connector);
    return (
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); signIn(); }}>
        <label className="block space-y-2">
          <span className="text-[15px] font-medium">{listen.label}</span>
          <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} placeholder={listen.placeholder} className={field} spellCheck={false} />
        </label>
        <Button type="submit" size="lg" className="h-11 w-full text-[15px]" disabled={busy || !value.trim()}>
          {busy ? <><Loader2 className="animate-spin" /> Waiting for {connector.name}</> : <>Sign in with {connector.name}</>}
        </Button>
        <p className="text-center text-sm text-muted-foreground">Read only. Turn off anytime.</p>
      </form>
    );
  }

  if (method === "webhook") {
    return (
      <div className="space-y-4">
        <p className="text-[15px]">Paste this URL into {connector.name === "Webhook" ? "the tool" : connector.name}.</p>
        <div className="flex items-center gap-2 rounded-xl border bg-surface p-1.5 pl-4">
          <code className="min-w-0 flex-1 truncate font-mono text-[13px]">{hook}</code>
          <Button size="sm" variant="ghost" onClick={() => { void navigator.clipboard?.writeText(hook); setCopied(true); }}>{copied ? <Check /> : <Copy />}{copied ? "Copied" : "Copy"}</Button>
        </div>
        <Button className="h-11 w-full text-[15px]" onClick={() => finish(hook)}>Done</Button>
      </div>
    );
  }

  if (method === "upload") {
    return (
      <div className="space-y-4">
        <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed bg-surface px-6 py-8 text-center transition-colors hover:border-primary/40">
          <Upload className="size-5 text-muted-foreground" aria-hidden />
          <span className="text-[15px] font-medium">{files.length ? `${files.length} file${files.length > 1 ? "s" : ""}` : "Choose files"}</span>
          <span className="text-sm text-muted-foreground">{files.length ? files.slice(0, 3).join(", ") : "CSV, PDF, Word, exports"}</span>
          <input type="file" multiple className="sr-only" onChange={(e) => setFiles(Array.from(e.target.files ?? []).map((f) => f.name))} />
        </label>
        <Button className="h-11 w-full text-[15px]" disabled={!files.length} onClick={() => finish(files.join(", "))}>Add</Button>
      </div>
    );
  }

  // database, mcp and website each need one line of text.
  const placeholder = method === "database" ? (DB_PLACEHOLDER[connector.id] ?? "protocol://readonly@host/db") : method === "mcp" ? "https://tool.example.com/mcp" : "https://yourcompany.com";
  const hint = method === "database" ? "Use a read-only user." : method === "mcp" ? "The brain reads through it." : "Public pages only.";
  const ok = method === "database" ? /^[a-z+]+:\/\/.+/i.test(value.trim()) : /^(https?:\/\/)?[^\s.]+\.[^\s]+$/i.test(value.trim());
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (!ok) return; setBusy(true); setTimeout(() => finish(method === "database" ? hostOf(value) : value.trim()), 800); }}>
      <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} placeholder={placeholder} aria-label={method === "database" ? "Connection link" : "URL"} className={cn(field, "font-mono text-[14px]")} spellCheck={false} />
      <p className="text-sm text-muted-foreground">{hint}</p>
      <Button type="submit" className="h-11 w-full text-[15px]" disabled={!ok || busy}>
        {busy ? <><Loader2 className="animate-spin" /> Checking</> : method === "database" ? "Test and connect" : "Connect"}
      </Button>
    </form>
  );
}

/** The host part of a database link, so a password in it is never shown back. */
function hostOf(link: string) {
  const m = link.trim().match(/@([^/;?]+)/);
  return m ? m[1] : link.trim().replace(/^[a-z+]+:\/\//i, "").split(/[/;?]/)[0];
}

function hashOf(s: string) {
  let h = 0;
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return h;
}

/** A small square with the category icon, standing in for a brand logo. */
export function ConnectorMark({ connector, className }: { connector: Connector; className?: string }) {
  // "Anything else" covers different kinds of thing, so those show how they connect instead.
  const Icon = connector.category === "other" ? METHOD[connector.method].icon : CATEGORY[connector.category].icon;
  return (
    <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground", className)} aria-hidden>
      <Icon className="size-[18px]" />
    </span>
  );
}
