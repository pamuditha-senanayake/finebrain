"use client";

import { Check, ChevronsUpDown, Plus, ShieldCheck, Trash2 } from "lucide-react";
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
import { FIELD_SPECS, KIND_LABEL, KIND_PLURAL, MEMBER_ORDER, describeCron, fieldLabel, isParam, type FieldSpec } from "@/lib/studio/spec";
import { cn } from "@/lib/utils";
import { KindIcon } from "./cards";
import { ProposalCard } from "./proposal-card";
import type { Focus } from "./state";

type Draft = { name: string; description: string; topics: string; status: ItemStatus; dri: string; fields: ItemFields };

const draftOf = (it: StudioItem | null, kind: MemberKind, dri: string): Draft => ({
  name: it?.name ?? "",
  description: it?.description ?? "",
  topics: it?.topics.join(", ") ?? "",
  status: it?.status ?? "active",
  dri: it?.dri ?? dri,
  fields: it ? structuredClone(it.fields) : Object.fromEntries(FIELD_SPECS[kind].map((s) => [s.key, s.type === "refs" || s.type === "list" ? [] : s.type === "boolean" ? s.key === "enabled" : s.type === "number" ? 0 : s.type === "select" ? (s.options?.[0] ?? "") : ""])),
});

/** Every part of the workflow as plain forms. Saving runs the same Edit Review Agent as the chat does. */
export function PartsView({ detail, focus, onFocus, onShowDiagram }: { detail: WorkflowDetail; focus: Focus; onFocus: (f: Focus) => void; onShowDiagram: (h: Highlight) => void }) {
  const [creating, setCreating] = useState<MemberKind | null>(null);
  const tools = useStudioTools();
  const selected = focus && focus.kind !== "workflow" ? detail.items.find((i) => i.id === focus.id) ?? (tools.data ?? []).find((t) => t.tool.id === focus.id)?.tool ?? null : null;
  const library = (tools.data ?? []).filter((t) => !detail.items.some((i) => i.id === t.tool.id));
  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-[240px_minmax(0,1fr)]">
      <nav className="min-h-0 overflow-y-auto rounded-xl border bg-card p-2 shadow-xs" aria-label="Workflow parts">
        {MEMBER_ORDER.map((k) => {
          const list = detail.items.filter((i) => i.kind === k);
          return (
            <div key={k} className="mb-2">
              <div className="flex items-center gap-1.5 px-1.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                <KindIcon kind={k} className="size-3" /> {KIND_PLURAL[k]}
                <Button size="icon-xs" variant="ghost" className="ml-auto" onClick={() => { setCreating(k); onFocus(null); }} aria-label={`New ${KIND_LABEL[k].toLowerCase()}`}>
                  <Plus />
                </Button>
              </div>
              <ul>
                {list.map((i) => (
                  <li key={i.id}>
                    <button type="button" onClick={() => { setCreating(null); onFocus({ kind: i.kind, id: i.id }); }} className={cn("min-h-6 w-full truncate rounded-md px-2 py-1 text-left text-xs hover:bg-accent", selected?.id === i.id && !creating && "bg-accent font-medium")} aria-current={selected?.id === i.id}>
                      {i.name} {i.status !== "active" && <span className="text-muted-foreground">({i.status})</span>}
                    </button>
                  </li>
                ))}
                {k === "tool" && library.length > 0 && (
                  <li className="mt-1 px-2 text-[10px] text-muted-foreground">
                    Library, not used here yet:
                    <ul>
                      {library.map((t) => (
                        <li key={t.tool.id}>
                          <button type="button" onClick={() => { setCreating(null); onFocus({ kind: "tool", id: t.tool.id }); }} className={cn("min-h-6 w-full truncate rounded-md px-2 py-0.5 text-left text-xs text-muted-foreground hover:bg-accent", selected?.id === t.tool.id && "bg-accent text-foreground")}>
                            {t.tool.name}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </li>
                )}
              </ul>
            </div>
          );
        })}
      </nav>
      <div className="min-h-0 overflow-y-auto rounded-xl border bg-card p-4 shadow-xs">
        {creating ? (
          <ItemForm key={`new-${creating}`} kind={creating} item={null} detail={detail} onShowDiagram={onShowDiagram} onDone={(r) => { setCreating(null); if (r.status === "applied") onFocus({ kind: creating, id: r.targetId }); }} />
        ) : selected ? (
          <ItemForm key={`${selected.id}@${selected.version}`} kind={selected.kind} item={selected} detail={detail} onShowDiagram={onShowDiagram} onDone={() => undefined} />
        ) : (
          <div className="grid h-full place-items-center text-center text-sm text-muted-foreground">
            <div>
              <p className="font-medium text-foreground">Pick a part on the left, or add one with +</p>
              <p className="mt-1 text-xs">Forms cover every field, including description and topics. Saving shows the Edit Review Agent&apos;s report before anything changes.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ItemForm({ kind, item, detail, onDone, onShowDiagram }: { kind: MemberKind; item: StudioItem | null; detail: WorkflowDetail; onDone: (r: ApplyResult) => void; onShowDiagram: (h: Highlight) => void }) {
  const { user } = useCurrentUser();
  const humans = useHumans();
  const tools = useStudioTools();
  const [d, setD] = useState<Draft>(() => draftOf(item, kind, detail.workflow.dri));
  const [reply, setReply] = useState<ChatReply | null>(null);
  const [applied, setApplied] = useState<ApplyResult | undefined>();
  const review = useStudioReview();
  const readOnly = user?.tier === "L3";
  const specs = FIELD_SPECS[kind];
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
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <KindIcon kind={kind} className="size-4" />
        <h2 className="flex-1 text-base font-semibold">{item ? item.name : `New ${KIND_LABEL[kind].toLowerCase()}`}</h2>
        {kind === "tool" && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary">Shared tool: edits reach every workflow that uses it</span>}
      </div>
      <fieldset disabled={readOnly} className="grid gap-3 md:grid-cols-2">
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
          <FormRow key={s.key} label={s.label} hint={s.key === "cron" ? describeCron(String(d.fields.cron ?? "")) : s.hint ?? (s.unit ? `In ${s.unit}` : undefined)} wide={s.type === "longtext" || s.key === "steps" || s.type === "refs"}>
            <FieldInput spec={s} value={d.fields[s.key]} onChange={(v) => setField(s.key, v)} options={s.ref ? options(s.ref) : []} />
          </FormRow>
        ))}
        {params.map((k) => (
          <FormRow key={k} label={fieldLabel("policy", k)} hint={k.endsWith("Minor") ? "In minor units (cents)" : undefined}>
            {typeof d.fields[k] === "boolean" ? <Switch checked={d.fields[k] as boolean} onCheckedChange={(v) => setField(k, v)} /> : <Input value={String(d.fields[k] ?? "")} onChange={(e) => setField(k, typeof item?.fields[k] === "number" ? Number(e.target.value) || 0 : e.target.value)} inputMode={typeof item?.fields[k] === "number" ? "numeric" : undefined} />}
          </FormRow>
        ))}
      </fieldset>
      {!readOnly && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={save} disabled={review.isPending}><ShieldCheck /> Review {item ? "changes" : "and create"}</Button>
          {item && (
            <Button variant="outline" className="text-risk" disabled={review.isPending} onClick={() => submit({ intent: "delete", kind, targetId: item.id, workflowId: item.workflowId ?? detail.workflow.id, patch: {} })}>
              <Trash2 /> Delete
            </Button>
          )}
          {review.error && <span className="self-center text-xs text-risk">{review.error.message}</span>}
        </div>
      )}
      {readOnly && <p className="text-xs text-muted-foreground">You are L3, so this is read only. Use the chat to suggest a change to the DRI.</p>}
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
