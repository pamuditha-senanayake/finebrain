"use client";

import { ArrowRight, Check, ChevronLeft, Plus, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { ConnectForm, ConnectorMark } from "@/features/connect/connect-form";
import { otherTool } from "@/features/connect/connector-picker";
import { ConnectorsList } from "@/features/connect/connectors-list";
import { CONNECTORS, connectorById, type Connector } from "@/lib/connect/catalog";
import { useConnect } from "@/lib/connect/store";
import { cn } from "@/lib/utils";

type Step = { kind: "name" | "website" | "about" | "tools" | "mcps" | "done" } | { kind: "connect"; connector: Connector };

/** The tools most businesses name first. The rest wait behind "More". */
const COMMON = ["gmail", "outlook", "slack", "teams", "github", "jira", "notion", "gdrive", "hubspot", "salesforce", "stripe", "shopify", "quickbooks", "postgres", "mysql"];

const field = "h-12 w-full rounded-xl border bg-background px-4 text-[16px] outline-none placeholder:text-muted-foreground focus-visible:ring-3 focus-visible:ring-ring/40";

function questionOf(step: Step, business: string) {
  switch (step.kind) {
    case "name": return "What is the business called?";
    case "website": return "What is the website?";
    case "about": return "What do you do, in one line?";
    case "tools": return "Which tools do you use today?";
    case "connect": return `Connect ${step.connector.name}?`;
    case "mcps": return "Any MCP servers you already use?";
    case "done": return `${business || "The brain"} is learning.`;
  }
}

const HINT: Partial<Record<Step["kind"], string>> = {
  website: "I will read it first.",
  tools: "Pick all that apply.",
  mcps: "Optional. Paste a URL.",
};

/**
 * Teaches the brain about a new business, one question at a time:
 * the name and website, what it does, the tools in use, a connector for each, then any MCP servers.
 * Every connection becomes a sensor, and what it reads flows into knowledge.
 * `variant="ask"` runs inside Ask the Brain, where `onQuestion` speaks each question.
 */
export function Interview({ variant = "page", onQuestion, onExit }: { variant?: "page" | "ask"; onQuestion?: (q: string) => void; onExit?: () => void }) {
  const { profile, step: at, setProfile, setStep, connections, connect } = useConnect();

  const steps: Step[] = useMemo(() => {
    const picked = profile.tools.map(connectorById).filter((c): c is Connector => !!c);
    const others = profile.other.split(",").map((s) => s.trim()).filter(Boolean).map(otherTool);
    return [{ kind: "name" }, { kind: "website" }, { kind: "about" }, { kind: "tools" }, ...[...picked, ...others].map((connector) => ({ kind: "connect" as const, connector })), { kind: "mcps" }, { kind: "done" }];
  }, [profile.tools, profile.other]);

  const i = Math.min(at, steps.length - 1);
  const step = steps[i];
  const question = questionOf(step, profile.name);
  const next = () => setStep(i + 1);
  const back = () => setStep(Math.max(0, i - 1));

  useEffect(() => {
    onQuestion?.(question);
    // Speak once per question, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question]);

  const ask = variant === "ask";
  return (
    <div className={cn("mx-auto w-full", ask ? "max-w-xl text-left" : "max-w-xl")}>
      <div className="mb-6 flex items-center gap-3">
        {i > 0 && step.kind !== "done" ? (
          <Button variant="ghost" size="sm" className="-ml-2 text-muted-foreground" onClick={back}><ChevronLeft /> Back</Button>
        ) : <span />}
        <div className="ml-auto flex items-center gap-3">
          {step.kind !== "done" && <span className="text-sm tabular-nums text-muted-foreground">{i + 1} of {steps.length - 1}</span>}
          {onExit && <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={onExit}>Exit</Button>}
        </div>
      </div>
      <div className="mb-8 h-1 overflow-hidden rounded-full bg-muted" aria-hidden>
        <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${(i / (steps.length - 1)) * 100}%` }} />
      </div>

      <h2 className={cn("font-semibold leading-snug tracking-tight", ask ? "text-2xl" : "text-[26px]")} aria-live="polite">{question}</h2>
      {HINT[step.kind] && <p className="mt-2 text-[15px] text-muted-foreground">{HINT[step.kind]}</p>}

      <div className="mt-8" key={i}>
        {step.kind === "name" && <TextStep value={profile.name} placeholder="Finebase" onNext={(v) => { setProfile({ name: v }); next(); }} required />}
        {step.kind === "website" && (
          <TextStep
            value={profile.website}
            placeholder="finebase.com"
            onNext={(v) => {
              setProfile({ website: v });
              if (v) connect({ connectorId: "website", name: "Website", method: "website", detail: v.replace(/^https?:\/\//, "") });
              next();
            }}
            skip
          />
        )}
        {step.kind === "about" && <TextStep value={profile.about} placeholder="We sell accounting software to small shops" onNext={(v) => { setProfile({ about: v }); next(); }} skip />}
        {step.kind === "tools" && <ToolsStep onNext={next} />}
        {step.kind === "connect" && <ConnectStep connector={step.connector} done={connections.some((c) => c.connectorId === step.connector.id && (step.connector.id !== "other" || c.name === step.connector.name))} onNext={next} />}
        {step.kind === "mcps" && <McpStep onNext={next} />}
        {step.kind === "done" && (
          <div className="space-y-6">
            <ConnectorsList title="Connected" />
            {!connections.length && <p className="text-[15px] text-muted-foreground">Nothing connected yet. Add connectors anytime.</p>}
            <div className="flex flex-wrap gap-2">
              {ask ? <Button size="lg" onClick={onExit}>Done</Button> : <Button asChild size="lg"><Link href="/l2/sensors">Open sensors <ArrowRight /></Link></Button>}
              <Button size="lg" variant="ghost" className="text-muted-foreground" onClick={() => setStep(0)}>Edit answers</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function TextStep({ value, placeholder, onNext, skip, required }: { value: string; placeholder: string; onNext: (v: string) => void; skip?: boolean; required?: boolean }) {
  const [v, setV] = useState(value);
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (required && !v.trim()) return; onNext(v.trim()); }}>
      <input autoFocus value={v} onChange={(e) => setV(e.target.value)} placeholder={placeholder} aria-label="Answer" className={field} />
      <div className="flex gap-2">
        <Button type="submit" size="lg" disabled={required && !v.trim()}>Next <ArrowRight /></Button>
        {skip && !v.trim() && <Button type="button" size="lg" variant="ghost" className="text-muted-foreground" onClick={() => onNext("")}>Skip</Button>}
      </div>
    </form>
  );
}

function ToolsStep({ onNext }: { onNext: () => void }) {
  const { profile, setProfile } = useConnect();
  const [more, setMore] = useState(false);
  const [other, setOther] = useState(profile.other);
  const shown = more ? CONNECTORS.filter((c) => c.category !== "other") : CONNECTORS.filter((c) => COMMON.includes(c.id) || profile.tools.includes(c.id));
  // Read the latest list, so quick clicks in a row never overwrite each other.
  const toggle = (id: string) => {
    const tools = useConnect.getState().profile.tools;
    setProfile({ tools: tools.includes(id) ? tools.filter((t) => t !== id) : [...tools, id] });
  };
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        {shown.map((c) => {
          const on = profile.tools.includes(c.id);
          return (
            <button key={c.id} type="button" onClick={() => toggle(c.id)} aria-pressed={on} className={cn("inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-[15px] transition-colors", on ? "border-primary bg-primary/10 text-foreground" : "bg-surface hover:bg-accent")}>
              {on && <Check className="size-4 text-primary" aria-hidden />}
              {c.name}
            </button>
          );
        })}
        {!more && <button type="button" onClick={() => setMore(true)} className="rounded-full px-4 py-2 text-[15px] text-muted-foreground hover:text-foreground">More…</button>}
      </div>
      <input value={other} onChange={(e) => setOther(e.target.value)} placeholder="Something else? e.g. Odoo, our own app" aria-label="Other tools" className={field} />
      <Button size="lg" onClick={() => { setProfile({ other }); onNext(); }}>Next <ArrowRight /></Button>
    </div>
  );
}

function ConnectStep({ connector, done, onNext }: { connector: Connector; done: boolean; onNext: () => void }) {
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-4 rounded-2xl border bg-card p-5">
        <ConnectorMark connector={connector} />
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-medium">{connector.name}</div>
          <div className="text-sm text-muted-foreground">{done ? "Connected" : connector.id === "other" ? "Not in our list yet" : "Becomes a sensor"}</div>
        </div>
        {done && <Check className="size-5 text-ok" aria-hidden />}
      </div>
      {done ? (
        <Button size="lg" onClick={onNext}>Next <ArrowRight /></Button>
      ) : (
        <>
          <ConnectForm connector={connector} onDone={onNext} />
          <Button variant="ghost" className="w-full text-muted-foreground" onClick={onNext}>Skip for now</Button>
        </>
      )}
    </div>
  );
}

function McpStep({ onNext }: { onNext: () => void }) {
  const { profile, setProfile, connect } = useConnect();
  const [url, setUrl] = useState("");
  const ok = /^https?:\/\/[^\s.]+\.[^\s]+$/i.test(url.trim());
  function add() {
    const u = url.trim();
    if (!ok || profile.mcps.includes(u)) return;
    setProfile({ mcps: [...profile.mcps, u] });
    connect({ connectorId: "mcp", name: new URL(u).hostname, method: "mcp", detail: u });
    setUrl("");
  }
  return (
    <div className="space-y-5">
      {profile.mcps.length > 0 && (
        <ul className="space-y-2">
          {profile.mcps.map((m) => (
            <li key={m} className="flex items-center gap-3 rounded-xl border bg-surface px-4 py-3">
              <Check className="size-4 text-ok" aria-hidden />
              <span className="min-w-0 flex-1 truncate font-mono text-[13px]">{m}</span>
              <Button variant="ghost" size="icon-sm" className="text-muted-foreground" onClick={() => setProfile({ mcps: profile.mcps.filter((x) => x !== m) })} aria-label={`Remove ${m}`}><X /></Button>
            </li>
          ))}
        </ul>
      )}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); add(); }}>
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://tool.example.com/mcp" aria-label="MCP server URL" className={cn(field, "font-mono text-[14px]")} spellCheck={false} />
        <Button type="submit" size="lg" variant="outline" className="h-12" disabled={!ok} aria-label="Add MCP server"><Plus /></Button>
      </form>
      <Button size="lg" onClick={onNext}>{profile.mcps.length ? "Next" : "None, finish"} <ArrowRight /></Button>
    </div>
  );
}

/** The Setup page: the interview on its own, centred. */
export function SetupPage() {
  return (
    <div className="py-6 sm:py-10">
      <h1 className="sr-only">Setup</h1>
      <Interview />
    </div>
  );
}
