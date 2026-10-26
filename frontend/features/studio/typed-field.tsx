"use client";

// typed-field.tsx: which typed input a Studio field gets, so every field the pipeline reads is picked from what exists:
// endpoints, capabilities and models from the server's options, a sensor's source and events, a skill's steps, a policy's
// date, currency and money, a scheduler's schedule and time zone. Null means the plain input is right (or no options
// came, as in a demo workspace, where the review still checks the value). Used by: parts.tsx.
import type { FieldValue, ItemFields, MemberKind, StudioOption, StudioOptions } from "@/contracts";
import { DateInput, MoneyInput, MultiPick, OptionSelect, TimezoneSelect } from "./field-inputs";
import { SchedulePicker } from "./schedule-picker";
import { SourceSelect } from "./source-select";
import { StepsEditor } from "./steps-editor";

type Props = { kind: MemberKind; field: string; fields: ItemFields; set: (key: string, value: FieldValue) => void; options?: StudioOptions; tools: StudioOption[] };

const text = (v: FieldValue | undefined) => String(v ?? "");
const list = (v: FieldValue | undefined) => (Array.isArray(v) ? v.map(String) : []);
const plain = (values: string[]) => values.map((v) => ({ id: v, label: v }));

/** Fields whose editor holds several controls: shown as a group, not inside one label. */
export const GROUPED = new Set(["skill.steps", "scheduler.cron"]);

export function typedField({ kind, field, fields, set, options, tools }: Props): React.ReactNode | null {
  const at = `${kind}.${field}`;
  const value = fields[field];
  // Steps, schedules, dates, time zones and sources need no server list
  if (at === "skill.steps") return <StepsEditor value={list(value)} onChange={(v) => set(field, v)} tools={tools} />;
  if (at === "scheduler.cron") return <SchedulePicker value={text(value)} onChange={(v) => set(field, v)} />;
  if (at === "scheduler.timezone") return <TimezoneSelect value={text(value)} onChange={(v) => set(field, v)} />;
  if (at === "policy.validFrom") return <DateInput value={text(value)} onChange={(v) => set(field, v)} label="Valid from" />;
  if (at === "sensor.source") return <SourceSelect value={text(value)} onChange={(v) => set(field, v)} />;
  if (at === "policy.param.amountMinor") return <MoneyInput minor={Number(value ?? 0)} onChange={(v) => set(field, v)} currency={text(fields["param.currency"])} label="Automatic limit" />;
  if (!options) return null;

  // The rest pick from what the pipeline really serves and checks
  if (at === "tool.endpoint" && fields.level !== "custom") return <OptionSelect value={text(value)} onChange={(v) => set(field, v)} options={options.endpoints} label="Endpoint" />;
  if (at === "tool.capability") return <OptionSelect value={text(value)} onChange={(v) => set(field, v)} options={options.capabilities} label="Required capability" noneLabel="None: any agent may use it" />;
  if (at === "agent.capabilities") return <MultiPick value={list(value)} onChange={(v) => set(field, v)} options={options.capabilities} label="Capabilities" />;
  if (at === "agent.model") return <OptionSelect value={text(value)} onChange={(v) => set(field, v)} options={options.models} label="Model" />;
  if (at === "policy.param.currency") return <OptionSelect value={text(value)} onChange={(v) => set(field, v)} options={plain(options.currencies)} label="Currency" />;
  const events = options.events[text(fields.source)];
  if (at === "sensor.events" && events) return <MultiPick value={list(value)} onChange={(v) => set(field, v)} options={plain(events)} label="Events" />;
  return null;
}

/** A short hint per typed field; the rest keep their spec's hint. */
export const TYPED_HINTS: Record<string, string> = {
  "sensor.source": "Wakes it", "tool.endpoint": "Where calls go", "agent.capabilities": "What it may do",
  "policy.param.amountMinor": "No approval below", "scheduler.timezone": "For the times",
};
