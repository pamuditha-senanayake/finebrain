"use client";

// field-inputs.tsx: Studio's typed inputs, so a field the pipeline reads can only hold a value that exists: a pick list and
// a multi pick from the server's real options (a value that is not one of them shows as such, never hidden), money in
// normal units stored as minor units, a date, and a searchable time zone. Used by: parts.tsx. Uses: components/ui.
import { Check, ChevronsUpDown } from "lucide-react";
import { useState } from "react";
import type { StudioOption } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

const NONE = "__none";

/** One choice from a real list. noneLabel allows an empty value; an unknown current value stays visible. */
export function OptionSelect({ value, onChange, options, label, noneLabel }: { value: string; onChange: (v: string) => void; options: StudioOption[]; label: string; noneLabel?: string }) {
  const known = options.some((o) => o.id === value);
  return (
    <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? "" : v)}>
      <SelectTrigger className="w-full" aria-label={label}><SelectValue /></SelectTrigger>
      <SelectContent>
        {(noneLabel || !value) && <SelectItem value={NONE}>{noneLabel ?? "Pick one"}</SelectItem>}
        {value && !known && <SelectItem value={value}>{value} (not known)</SelectItem>}
        {options.map((o) => <SelectItem key={o.id} value={o.id}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

/** Several choices from a real list, shown as chips. */
export function MultiPick({ value, onChange, options, label }: { value: string[]; onChange: (v: string[]) => void; options: StudioOption[]; label: string }) {
  const labels = new Map(options.map((o) => [o.id, o.label]));
  const all = [...options, ...value.filter((v) => !labels.has(v)).map((v) => ({ id: v, label: `${v} (not known)` }))];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" className="h-auto min-h-9 w-full justify-between py-1.5 text-left font-normal" aria-label={label}>
          <span className="flex flex-wrap gap-1">
            {value.length === 0 ? <span className="text-muted-foreground">None</span> : value.map((v) => <span key={v} className={cn("rounded bg-muted px-1.5 py-0.5 text-xs", !labels.has(v) && "text-risk")}>{labels.get(v) ?? `${v} (not known)`}</span>)}
          </span>
          <ChevronsUpDown className="size-3.5 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="max-h-72 w-72 overflow-y-auto p-1" align="start">
        {all.map((o) => {
          const on = value.includes(o.id);
          return (
            <button key={o.id} type="button" aria-pressed={on} onClick={() => onChange(on ? value.filter((x) => x !== o.id) : [...value, o.id])}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-accent focus-visible:bg-accent focus-visible:outline-none">
              <span className={cn("grid size-4 shrink-0 place-items-center rounded border", on && "border-primary bg-primary text-primary-foreground")}>{on && <Check className="size-3" />}</span>
              <span className="truncate">{o.label}</span>
            </button>
          );
        })}
      </PopoverContent>
    </Popover>
  );
}

/** Money in normal units (50,000.00), kept as minor units (5000000) because S7 compares minor units. */
export function MoneyInput({ minor, onChange, currency, label }: { minor: number; onChange: (v: number) => void; currency: string; label: string }) {
  const [text, setText] = useState(() => (minor / 100).toFixed(2));
  const commit = () => {
    const major = Number(text.replace(/,/g, ""));
    if (Number.isFinite(major) && major >= 0) onChange(Math.round(major * 100));
    setText((Number.isFinite(major) && major >= 0 ? major : minor / 100).toFixed(2));
  };
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-muted-foreground">{currency || "—"}</span>
      <Input value={text} inputMode="decimal" aria-label={label} onChange={(e) => setText(e.target.value)} onBlur={commit} />
    </div>
  );
}

/** A calendar date, stored as YYYY-MM-DD. */
export function DateInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return <Input type="date" value={value.slice(0, 10)} onChange={(e) => onChange(e.target.value)} aria-label={label} />;
}

/** A time zone from the browser's own list, searchable. */
export function TimezoneSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = useState(false);
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [value || "UTC"];
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" className="w-full justify-between font-normal" aria-label="Time zone">
          <span className={cn(!value && "text-muted-foreground")}>{value || "Pick a time zone"}</span>
          <ChevronsUpDown className="size-3.5 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0" align="start">
        <Command>
          <CommandInput placeholder="Search, e.g. Colombo" />
          <CommandList>
            <CommandEmpty>No time zone found.</CommandEmpty>
            {zones.map((zone) => (
              <CommandItem key={zone} value={zone} onSelect={() => { onChange(zone); setOpen(false); }}>
                <Check className={cn("size-3.5", zone === value ? "opacity-100" : "opacity-0")} />{zone}
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
