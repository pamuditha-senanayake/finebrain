"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { PageHeader, SampleBadge } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CLAUDE_TOOLS, useConnect } from "@/lib/connect/store";
import { useUi } from "@/lib/store";

/**
 * The brain as an MCP server, so Claude (app, web or Claude Code) can ask it directly.
 * Claude signs in with the person's own Company Brain account, so it sees only what they may see.
 */
export function ClaudeMcp() {
  const tenantId = useUi((s) => s.tenantId);
  const tools = useConnect((s) => s.claudeTools);
  const setTool = useConnect((s) => s.setClaudeTool);
  const url = `https://mcp.companybrain.app/${tenantId}`;
  const code = `claude mcp add --transport http company-brain ${url}`;
  const json = JSON.stringify({ mcpServers: { "company-brain": { command: "npx", args: ["-y", "mcp-remote", url] } } }, null, 2);

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Use in Claude" description="Ask the brain from Claude." />

      <section className="rounded-2xl border bg-card p-6">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-[15px] font-semibold">Server URL</h2>
          <SampleBadge />
        </div>
        <CopyLine text={url} />
      </section>

      <Tabs defaultValue="app" className="mt-6 rounded-2xl border bg-card p-6">
        <TabsList>
          <TabsTrigger value="app">Claude app</TabsTrigger>
          <TabsTrigger value="code">Claude Code</TabsTrigger>
          <TabsTrigger value="other">Other apps</TabsTrigger>
        </TabsList>
        <TabsContent value="app" className="pt-5">
          <Steps items={["Settings, then Connectors", "Add custom connector", "Paste the URL", "Sign in with Company Brain"]} />
        </TabsContent>
        <TabsContent value="code" className="space-y-4 pt-5">
          <CopyLine text={code} />
          <Steps items={["Run this in a terminal", "Type /mcp in Claude Code", "Sign in with Company Brain"]} />
        </TabsContent>
        <TabsContent value="other" className="space-y-4 pt-5">
          <CopyLine text={json} block />
          <Steps items={["Add this to the app's MCP config", "Restart the app", "Sign in with Company Brain"]} />
        </TabsContent>
      </Tabs>

      <section className="mt-6 rounded-2xl border bg-card p-6">
        <h2 className="text-[15px] font-semibold">What Claude can do</h2>
        <p className="mt-1 text-sm text-muted-foreground">Each person sees only what they can see here.</p>
        <ul className="mt-4 divide-y">
          {CLAUDE_TOOLS.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-4 py-3">
              <div>
                <div className="text-[15px]">{t.label}</div>
                {"hint" in t && <div className="text-[13px] text-muted-foreground">{t.hint}</div>}
              </div>
              <Switch checked={tools[t.id] ?? t.on} onCheckedChange={(v) => setTool(t.id, v)} aria-label={t.label} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Steps({ items }: { items: string[] }) {
  return (
    <ol className="space-y-3">
      {items.map((s, i) => (
        <li key={s} className="flex items-center gap-3 text-[15px]">
          <span className="grid size-6 shrink-0 place-items-center rounded-full bg-muted text-xs font-medium tabular-nums">{i + 1}</span>
          {s}
        </li>
      ))}
    </ol>
  );
}

function CopyLine({ text, block = false }: { text: string; block?: boolean }) {
  const [copied, setCopied] = useState(false);
  function copy() {
    void navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <div className="flex items-start gap-2 rounded-xl border bg-surface p-1.5 pl-4">
      {block ? <pre className="min-w-0 flex-1 overflow-x-auto py-2 font-mono text-[13px] leading-relaxed">{text}</pre> : <code className="min-w-0 flex-1 truncate py-1.5 font-mono text-[13px]">{text}</code>}
      <Button size="sm" variant="ghost" onClick={copy} aria-label="Copy">{copied ? <Check /> : <Copy />}{copied ? "Copied" : "Copy"}</Button>
    </div>
  );
}
