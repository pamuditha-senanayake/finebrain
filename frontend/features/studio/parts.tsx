"use client";

import { Check, ChevronsUpDown, ShieldCheck, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import type { ApplyResult, ChatReply, FieldValue, ItemFields, ItemStatus, MemberKind, ProposalInput, StudioItem, WorkflowDetail } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useHumans, useStudioReview, useStudioTools } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import type { Highlight } from "@/lib/studio/graph";
import { FIELD_SPECS, KIND_LABEL, TOOL_LEVEL_LABEL, describeCron, fieldLabel, isParam, visibleSpecs, type FieldSpec } from "@/lib/studio/spec";
import { cn } from "@/lib/utils";
import { KindIcon } from "./cards";
import { ProposalCard } from "./proposal-card";
import { SourceSelect } from "./source-select";

type Draft = { name: string; description: string; topics: string; status: ItemStatus; dri: string; fields: ItemFields };

const draftOf = (it: StudioItem | null, kind: MemberKind, dri: string): Draft => ({
  name: it?.name ?? "",
  description: it?.description ?? "",
  topics: it?.topics.join(", ") ?? "",
  status: it?.status ?? "active",
  dri: it?.dri ?? dri,
  fields: it ? structuredClone(it.fields) : Object.fromEntries(FIELD_SPECS[kind].map((s) => [s.key, s.type === "refs" || s.type === "list" ? [] : s.type === "boolean" ? s.key === "enabled" : s.type === "number" ? 0 : s.type === "select" ? (s.options?.[0] ?? "") : ""])),
});

/** One part as a plain form. Saving runs the same Edit Review Agent as the chat does. */
export function ItemForm({ kind, item, detail, onDone, onCancel, onShowDiagram }: { kind: MemberKind; item: StudioItem | null; detail: WorkflowDetail; onDone: (r: ApplyResult) => void; onCancel?: () => void; onShowDiagram: (h: Highlight) => void }) {
  const { user } = useCurrentUser();
  const humans = useHumans();
  const tools = useStudioTools();
  const [d, setD] = useState<Draft>(() => draftOf(item, kind, detail.workflow.dri));
  const [reply, setReply] = useState<ChatReply | null>(null);
  const [applied, setApplied] = useState<ApplyResult | undefined>();
  const review = useStudioReview();
  const readOnly = user?.tier === "L3";
  const specs = visibleSpecs(kind, d.fields).filter((s) => s.key !== "code");
  const hasCode = kind === "tool" && d.fields.level === "custom";
  const params = Object.keys(d.fields).filter(isParam);
  const setField = (k: string, v: FieldValue) => setD((x) => ({ ...x, fields: { ...x.fields, [k]: v } }));
  const options = (ref: MemberKind) => (ref === "tool" ? (tools.data ?? []).map((t) => t.tool) : detail.items.filter((i) => i.kind === ref));

  const submit = (input: ProposalInput) => review.mutate({ input, workflowId: detail.workflow.id }, { onSuccess: (r) => { setApplied(undefined); setReply(r); } });
  const save = () => {
    const patch: ProposalInput["patch"] = {
      name: d.name.trim() || `New ${KIND_LABEL[kind].toLowerCase()}`,
      description: d.description,
      topics: d.topics.split(",").map((t) => t.trim()).filter(Boolean),
      status: d.status,
      dri: d.dri,
      fields: d.fields,
    };
    submit({ intent: item ? "update" : "create", kind, targetId: item?.id ?? null, workflowId: kind === "tool" ? null : detail.workflow.id, patch });
  };

  return (
    <div className="space-y-5">
      {!item && (
        <div className="flex items-center gap-2">
          <KindIcon kind={kind} className="size-4" />
          <h3 className="text-sm font-semibold">New {KIND_LABEL[kind].toLowerCase()}</h3>
        </div>
      )}
      {kind === "tool" && <p className="text-xs text-muted-foreground">Shared tool. Edits reach every workflow that uses it.</p>}
      <fieldset disabled={readOnly} className="grid gap-x-4 gap-y-4 md:grid-cols-2">
        <FormRow label="Name"><Input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} /></FormRow>
        <FormRow label="Status">
          <Select value={d.status} onValueChange={(v) => setD({ ...d, status: v as ItemStatus })}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>{["active", "draft", "paused", "retired"].map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
          </Select>
        </FormRow>
        <FormRow label="Description" wide><Textarea value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} className="min-h-16" /></FormRow>
        <FormRow label="Topics" hint="Comma separated"><Input value={d.topics} onChange={(e) => setD({ ...d, topics: e.target.value })} /></FormRow>
        <FormRow label="DRI">
          <Select value={d.dri} onValueChange={(v) => setD({ ...d, dri: v })}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>{(humans.data ?? []).filter((h) => h.tier !== "L3").map((h) => <SelectItem key={h.id} value={h.id}>{h.name}</SelectItem>)}</SelectContent>
          </Select>
        </FormRow>
        {specs.map((s) => (
          <FormRow key={s.key} label={s.label} hint={s.key === "cron" ? describeCron(String(d.fields.cron ?? "")) : kind === "sensor" && s.key === "source" ? "The connection whose messages wake this workflow" : s.hint ?? (s.unit ? `In ${s.unit}` : undefined)} wide={s.type === "longtext" || s.key === "steps" || s.type === "refs"}>
            {s.key === "level" ? <LevelSelect value={String(d.fields.level ?? "prebuilt")} onChange={(v) => setField("level", v)} />
              : kind === "sensor" && s.key === "source" ? <SourceSelect value={String(d.fields.source ?? "")} onChange={(v) => setField("source", v)} />
              : <FieldInput spec={s} value={d.fields[s.key]} onChange={(v) => setField(s.key, v)} options={s.ref ? options(s.ref) : []} />}
          </FormRow>
        ))}
        {params.map((k) => (
          <FormRow key={k} label={fieldLabel("policy", k)} hint={k.endsWith("Minor") ? "In minor units (cents)" : undefined}>
            {typeof d.fields[k] === "boolean" ? <Switch checked={d.fields[k] as boolean} onCheckedChange={(v) => setField(k, v)} /> : <Input value={String(d.fields[k] ?? "")} onChange={(e) => setField(k, typeof item?.fields[k] === "number" ? Number(e.target.value) || 0 : e.target.value)} inputMode={typeof item?.fields[k] === "number" ? "numeric" : undefined} />}
          </FormRow>
        ))}
        {hasCode && (
          <details className="group md:col-span-2">
            <summary className="cursor-pointer select-none text-xs font-medium text-muted-foreground hover:text-foreground">Advanced: code</summary>
            <Textarea value={String(d.fields.code ?? "")} onChange={(e) => setField("code", e.target.value)} className="mt-2 min-h-40 font-mono text-xs" aria-label="Code" spellCheck={false} />
            <p className="mt-1 text-[11px] text-muted-foreground">Runs in a sandbox. The review runs a test before anything uses it.</p>
          </details>
        )}
      </fieldset>
      {!readOnly && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button onClick={save} disabled={review.isPending}><ShieldCheck /> Review {item ? "changes" : "and create"}</Button>
          {onCancel && <Button variant="ghost" onClick={onCancel}>Cancel</Button>}
          {item && (
            <Button variant="ghost" className="ml-auto text-risk" disabled={review.isPending} onClick={() => submit({ intent: "delete", kind, targetId: item.id, workflowId: item.workflowId ?? detail.workflow.id, patch: {} })}>
              <Trash2 /> Delete
            </Button>
          )}
          {review.error && <span className="text-xs text-risk">{review.error.message}</span>}
        </div>
      )}
      {readOnly && <p className="text-xs text-muted-foreground">Read only for L3. Suggest a change in the chat.</p>}
      <Dialog open={!!reply} onOpenChange={(o) => !o && setReply(null)}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>Review before saving</DialogTitle>
            <DialogDescription>{reply?.answer}</DialogDescription>
          </DialogHeader>
          {reply?.proposal && (
            <ProposalCard
              proposal={reply.proposal}
              detail={detail}
              applied={applied}
              onApplied={(r) => { setApplied(r); toast.success(r.message); onDone(r); }}
              onFix={(s) => s.input && submit(s.input)}
              onShowDiagram={(h) => { setReply(null); onShowDiagram(h); }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function LevelSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
      <SelectContent>{Object.entries(TOOL_LEVEL_LABEL).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
    </Select>
  );
}

function FormRow({ label, hint, wide, children }: { label: string; hint?: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <label className={cn("block space-y-1", wide && "md:col-span-2")}>
      <span className="flex items-baseline justify-between gap-2 text-xs font-medium">
        {label}
        {hint && <span className="truncate text-[11px] font-normal text-muted-foreground">{hint}</span>}
      </span>
      {children}
    </label>
  );
}

function FieldInput({ spec, value, onChange, options }: { spec: FieldSpec; value: FieldValue | undefined; onChange: (v: FieldValue) => void; options: StudioItem[] }) {
  if (spec.type === "boolean") return <div><Switch checked={value === true} onCheckedChange={onChange} aria-label={spec.label} /></div>;
  if (spec.type === "number") return <Input type="number" value={String(value ?? 0)} onChange={(e) => onChange(Number(e.target.value) || 0)} />;
  if (spec.type === "longtext") return <Textarea value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} className="min-h-16" />;
  if (spec.type === "list") return <Textarea value={(Array.isArray(value) ? value : []).join("\n")} onChange={(e) => onChange(e.target.value.split("\n"))} onBlur={(e) => onChange(e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} className="min-h-16 font-mono text-xs" placeholder="One per line" />;
  if (spec.type === "select")
    return (
      <Select value={String(value ?? "")} onValueChange={onChange}>
        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent>{(spec.options ?? []).map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
      </Select>
    );
  if (spec.type === "ref")
    return (
      <Select value={String(value || "__none")} onValueChange={(v) => onChange(v === "__none" ? "" : v)}>
        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="__none">None</SelectItem>
          {options.map((o) => <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>)}
        </SelectContent>
      </Select>
    );
  if (spec.type === "refs") return <MultiRef value={Array.isArray(value) ? value : []} onChange={onChange} options={options} label={spec.label} />;
  return <Input value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />;
}

function MultiRef({ value, onChange, options, label }: { value: string[]; onChange: (v: string[]) => void; options: StudioItem[]; label: string }) {
  const names = useMemo(() => new Map(options.map((o) => [o.id, o.name])), [options]);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" className="h-auto min-h-9 w-full justify-between py-1.5 text-left font-normal" aria-label={label}>
          <span className="flex flex-wrap gap-1">
            {value.length === 0 ? <span className="text-muted-foreground">None</span> : value.map((id) => <span key={id} className="rounded bg-muted px-1.5 py-0.5 text-xs">{names.get(id) ?? id}</span>)}
          </span>
          <ChevronsUpDown className="size-3.5 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="max-h-72 w-72 overflow-y-auto p-1" align="start">
        {options.length === 0 && <p className="p-2 text-xs text-muted-foreground">Nothing of this kind in the workflow yet.</p>}
        {options.map((o) => {
          const on = value.includes(o.id);
          return (
            <button key={o.id} type="button" className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-accent" onClick={() => onChange(on ? value.filter((x) => x !== o.id) : [...value, o.id])} aria-pressed={on}>
              <span className={cn("grid size-4 place-items-center rounded border", on && "border-primary bg-primary text-primary-foreground")}>{on && <Check className="size-3" />}</span>
              <span className="truncate">{o.name}</span>
            </button>
          );
        })}
      </PopoverContent>
    </Popover>
  );
}
