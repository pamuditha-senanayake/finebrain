"use client";

// steps-editor.tsx: a skill's steps as rows (what kind of step, what it does, and for a tool step which of the skill's
// tools), so nobody has to remember "kind: text [tool:id]". It still reads and writes that format, which the pipeline
// stores. A step naming a tool the skill does not list shows as such. Used by: parts.tsx. Uses: components/ui.
import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";
import type { StudioOption } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const KINDS: StudioOption[] = [{ id: "judgment", label: "Decide" }, { id: "retrieval", label: "Look up" }, { id: "tool", label: "Tool" }, { id: "quality_gate", label: "Check" }];
const LINE = /^(judgment|retrieval|tool|quality_gate):\s*(.*?)\s*(?:\[(tool:[^\]]+)\])?\s*$/;

type Step = { kind: string; text: string; tool: string };

export const parseStep = (line: string): Step => {
  const m = LINE.exec(line);
  return m ? { kind: m[1], text: m[2], tool: m[3] ?? "" } : { kind: "judgment", text: line.trim(), tool: "" };
};
export const writeStep = (s: Step) => `${s.kind}: ${s.text.trim()}${s.kind === "tool" && s.tool ? ` [${s.tool}]` : ""}`;

export function StepsEditor({ value, onChange, tools }: { value: string[]; onChange: (v: string[]) => void; tools: StudioOption[] }) {
  const steps = value.map(parseStep);
  const save = (next: Step[]) => onChange(next.map(writeStep));
  const set = (i: number, patch: Partial<Step>) => save(steps.map((s, n) => (n === i ? { ...s, ...patch } : s)));
  const move = (i: number, by: number) => {
    const next = [...steps];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    save(next);
  };
  return (
    <div className="space-y-2">
      {steps.length === 0 && <p className="text-xs text-muted-foreground">No steps yet. Add the first thing the agent does.</p>}
      {steps.map((s, i) => (
        <div key={i} className="space-y-2 rounded-lg border p-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="w-4 shrink-0 text-center text-xs text-muted-foreground" aria-hidden>{i + 1}</span>
            <Select value={s.kind} onValueChange={(v) => set(i, { kind: v })}>
              <SelectTrigger className={s.kind === "tool" ? "w-24 shrink-0" : "min-w-0 flex-1"} aria-label={`Step ${i + 1} kind`}><SelectValue /></SelectTrigger>
              <SelectContent>{KINDS.map((k) => <SelectItem key={k.id} value={k.id}>{k.label}</SelectItem>)}</SelectContent>
            </Select>
            {s.kind === "tool" && (
              <Select value={s.tool || "__none"} onValueChange={(v) => set(i, { tool: v === "__none" ? "" : v })}>
                <SelectTrigger className="min-w-0 flex-1" aria-label={`Step ${i + 1} tool`}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">Pick a tool</SelectItem>
                  {s.tool && !tools.some((t) => t.id === s.tool) && <SelectItem value={s.tool}>{s.tool.replace("tool:", "")} (not in this skill)</SelectItem>}
                  {tools.map((t) => <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
            <span className="flex shrink-0">
              <Button type="button" size="icon-sm" variant="ghost" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Move step ${i + 1} up`}><ArrowUp /></Button>
              <Button type="button" size="icon-sm" variant="ghost" disabled={i === steps.length - 1} onClick={() => move(i, 1)} aria-label={`Move step ${i + 1} down`}><ArrowDown /></Button>
              <Button type="button" size="icon-sm" variant="ghost" onClick={() => save(steps.filter((_, n) => n !== i))} aria-label={`Remove step ${i + 1}`}><X /></Button>
            </span>
          </div>
          <Input value={s.text} onChange={(e) => set(i, { text: e.target.value })} placeholder="What the agent does" aria-label={`Step ${i + 1}`} />
        </div>
      ))}
      <Button type="button" size="sm" variant="outline" onClick={() => save([...steps, { kind: "judgment", text: "", tool: "" }])}><Plus /> Add step</Button>
      {tools.length === 0 && <p className="text-[11px] text-muted-foreground">Pick the skill&apos;s tools first to use them in a step.</p>}
    </div>
  );
}
