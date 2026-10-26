"use client";

// schedule-picker.tsx: a scheduler's cron as plain choices (every hour, every day, weekdays, one day a week, one day a
// month) plus a time, written back as the cron the pipeline stores. Anything else stays editable under Custom, so an
// existing schedule is never lost. Used by: parts.tsx. Uses: components/ui, lib/studio/spec.ts (describeCron).
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { describeCron } from "@/lib/studio/spec";

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MODES = [["hourly", "Every hour"], ["daily", "Every day"], ["weekdays", "Weekdays"], ["weekly", "One day a week"], ["monthly", "One day a month"], ["custom", "Custom"]] as const;
type Mode = (typeof MODES)[number][0];
type Plan = { mode: Mode; time: string; day: string; custom: string };

const pad = (n: string) => n.padStart(2, "0");

export function planOf(cron: string): Plan {
  const [m = "", h = "", dom = "", , dow = ""] = cron.trim().split(/\s+/);
  const timed = /^\d+$/.test(m) && /^\d+$/.test(h);
  const time = timed ? `${pad(h)}:${pad(m)}` : "09:00";
  const base = { time, day: "1", custom: cron };
  if (h === "*" && /^\d+$/.test(m) && dom === "*" && dow === "*") return { ...base, mode: "hourly", time: `00:${pad(m)}` };
  if (timed && dom === "*" && dow === "*") return { ...base, mode: "daily" };
  if (timed && dom === "*" && dow === "1-5") return { ...base, mode: "weekdays" };
  if (timed && dom === "*" && /^[0-6]$/.test(dow)) return { ...base, mode: "weekly", day: dow };
  if (timed && /^\d+$/.test(dom) && dow === "*") return { ...base, mode: "monthly", day: dom };
  return { ...base, mode: cron.trim() ? "custom" : "daily" };
}

export function cronOf(p: Plan): string {
  const [h, m] = p.time.split(":").map((x) => String(Number(x) || 0));
  return { hourly: `${m} * * * *`, daily: `${m} ${h} * * *`, weekdays: `${m} ${h} * * 1-5`, weekly: `${m} ${h} * * ${p.day}`, monthly: `${m} ${h} ${p.day} * *`, custom: p.custom }[p.mode];
}

export function SchedulePicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [plan, setPlan] = useState(() => planOf(value));
  const update = (patch: Partial<Plan>) => {
    const next = { ...plan, ...patch };
    setPlan(next);
    onChange(cronOf(next));
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Select value={plan.mode} onValueChange={(v) => update({ mode: v as Mode, day: v === "weekly" ? "1" : v === "monthly" ? "1" : plan.day })}>
          <SelectTrigger className="w-40" aria-label="How often"><SelectValue /></SelectTrigger>
          <SelectContent>{MODES.map(([id, label]) => <SelectItem key={id} value={id}>{label}</SelectItem>)}</SelectContent>
        </Select>
        {plan.mode === "weekly" && (
          <Select value={plan.day} onValueChange={(v) => update({ day: v })}>
            <SelectTrigger className="w-36" aria-label="Day of the week"><SelectValue /></SelectTrigger>
            <SelectContent>{DAYS.map((d, i) => <SelectItem key={d} value={String(i)}>{d}</SelectItem>)}</SelectContent>
          </Select>
        )}
        {plan.mode === "monthly" && (
          <Select value={plan.day} onValueChange={(v) => update({ day: v })}>
            <SelectTrigger className="w-28" aria-label="Day of the month"><SelectValue /></SelectTrigger>
            <SelectContent>{Array.from({ length: 28 }, (_, i) => String(i + 1)).map((d) => <SelectItem key={d} value={d}>Day {d}</SelectItem>)}</SelectContent>
          </Select>
        )}
        {plan.mode === "hourly" && <Input type="number" min={0} max={59} className="w-24" aria-label="Minute past the hour" value={Number(plan.time.split(":")[1])} onChange={(e) => update({ time: `00:${pad(String(Math.min(59, Math.max(0, Number(e.target.value) || 0))))}` })} />}
        {!["hourly", "custom"].includes(plan.mode) && <Input type="time" className="w-32" aria-label="Time" value={plan.time} onChange={(e) => update({ time: e.target.value || "09:00" })} />}
      </div>
      {plan.mode === "custom" && <Input value={plan.custom} onChange={(e) => update({ custom: e.target.value })} className="font-mono text-xs" aria-label="Cron" placeholder="minute hour day month weekday" />}
      <p className="text-[11px] text-muted-foreground">{describeCron(cronOf(plan)) || "Not set"}</p>
    </div>
  );
}
