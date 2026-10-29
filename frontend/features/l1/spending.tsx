"use client";

// spending.tsx: A4, what the company pays for. The month against the budget first (a meter with its state in words),
// then six months, then this month by category, the subscriptions, and every spend. Receipts added through Lisena land
// here; a spend can also be added by hand. Totals only, no advice. Used by: app/(l1)/l1/spending/page.tsx.
// Uses: lib/api/spending.ts, backend spending.py and the "Spending" workflow in Studio.
import { AlertTriangle, CheckCircle2, Plus, Receipt, XCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { Spend, SpendingSummary } from "@/contracts";
import { PageHeader, QueryView, Section } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAddSpend, useRemoveSpend, useSpending } from "@/lib/api/spending";
import { date } from "@/lib/format";
import { cn } from "@/lib/utils";

// Config
const STATE = {
  ok: { label: "On track", icon: CheckCircle2, tone: "text-muted-foreground", bar: "bg-primary" },
  close: { label: "Close to budget", icon: AlertTriangle, tone: "text-warn-fg", bar: "bg-warn" },
  over: { label: "Over budget", icon: XCircle, tone: "text-risk", bar: "bg-risk" },
} as const;
const CATEGORIES = { software: "Software and tools", cloud: "Cloud and hosting", people: "People and contractors", office: "Office", travel: "Travel", marketing: "Marketing", fees: "Bank and legal fees", other: "Other" };
const REPEATS = { once: "Just once", monthly: "Every month", yearly: "Every year" };
const CURRENCIES = ["USD", "LKR", "EUR", "GBP"];

const money = (currency: string, amount: number) => `${currency} ${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const monthName = (month: string, style: "short" | "long" = "short") => new Date(`${month}-01T00:00:00`).toLocaleDateString(undefined, { month: style, ...(style === "long" ? { year: "numeric" } : {}) });

export function SpendingView() {
  const spending = useSpending();
  const [adding, setAdding] = useState(false);
  return (
    <div>
      <PageHeader title="Spending" description="What the company pays for, against the monthly budget." actions={<Button onClick={() => setAdding(true)}><Plus /> Add spend</Button>} />
      <QueryView query={spending}>
        {(s) => (s.spends.length === 0 ? <Empty onAdd={() => setAdding(true)} /> : <Overview s={s} />)}
      </QueryView>
      <AddSpend open={adding} onOpenChange={setAdding} />
    </div>
  );
}

function Overview({ s }: { s: SpendingSummary }) {
  return (
    <div className="space-y-10">
      <Meter s={s} />
      <div className="grid gap-10 lg:grid-cols-2">
        <Months s={s} />
        <Categories s={s} />
      </div>
      {s.subscriptions.length > 0 && (
        <Section title="Subscriptions" plain>
          <ul className="divide-y overflow-hidden rounded-xl border bg-card">
            {s.subscriptions.map((sub) => (
              <li key={sub.id} className="flex items-center gap-3 px-4 py-3">
                <span className="min-w-0 flex-1 truncate text-[15px] font-medium">{sub.vendor}</span>
                <span className="text-sm text-muted-foreground">{REPEATS[sub.repeats]}</span>
                <span className="w-32 text-right text-[15px] tabular-nums">{money(sub.currency, sub.perMonth)}<span className="text-xs text-muted-foreground"> /mo</span></span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Section title="Every spend" plain>
        <SpendList spends={s.spends} />
      </Section>
      <p className="text-xs text-muted-foreground">Totals only. For tax or finance advice, ask your accountant.</p>
    </div>
  );
}

/** This month: the spend, the budget, and the state in words and an icon, never by colour alone. */
function Meter({ s }: { s: SpendingSummary }) {
  const state = STATE[s.month.state];
  const Icon = state.icon;
  const width = Math.min(100, s.month.usedPercent);
  return (
    <section className="rounded-2xl border bg-card p-6" aria-labelledby="spend-month">
      <h2 id="spend-month" className="text-sm text-muted-foreground">{monthName(s.month.month, "long")}</h2>
      <p className="mt-2 text-3xl font-semibold tabular-nums tracking-tight">{money(s.budget.currency, s.month.spent)}</p>
      <p className="mt-1 text-sm text-muted-foreground">of {money(s.budget.currency, s.budget.monthly)} budget · {s.month.usedPercent.toFixed(0)}% used</p>
      <div className="relative mt-5 h-2 rounded-full bg-muted" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(s.month.usedPercent)} aria-label="Budget used">
        <div className={cn("h-full rounded-full transition-[width]", state.bar)} style={{ width: `${width}%` }} />
        <span className="absolute -top-1 h-4 w-0.5 rounded bg-foreground/40" style={{ left: `${s.budget.warnPercent}%` }} aria-hidden title={`Close at ${s.budget.warnPercent}%`} />
      </div>
      <p className={cn("mt-3 flex items-center gap-1.5 text-sm font-medium", state.tone)}><Icon className="size-4" aria-hidden /> {state.label}</p>
      {s.month.otherCurrencies.length > 0 && <p className="mt-2 text-xs text-muted-foreground">Spends in {s.month.otherCurrencies.join(", ")} this month are listed below but not counted in the budget.</p>}
    </section>
  );
}

/** Six months, one bar each; this month in the accent. Hover or focus a bar for its total. */
function Months({ s }: { s: SpendingSummary }) {
  const top = Math.max(s.budget.monthly, ...s.months.map((m) => m.spent), 1);
  const now = s.months[s.months.length - 1]?.month;
  return (
    <Section title="Last six months">
      <ol className="flex h-40 items-end gap-2" aria-label={`Monthly totals in ${s.budget.currency}`}>
        {s.months.map((m) => (
          <li key={m.month} className="group flex h-full flex-1 flex-col items-center justify-end gap-2" tabIndex={0} title={`${monthName(m.month, "long")}: ${money(s.budget.currency, m.spent)}`}>
            <span className="text-xs tabular-nums text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus:opacity-100">{Math.round(m.spent).toLocaleString()}</span>
            <span className={cn("w-full max-w-10 rounded-t-[4px]", m.month === now ? "bg-primary" : "bg-foreground/20")} style={{ height: `${(m.spent / top) * 100}%`, minHeight: m.spent ? 2 : 0 }} />
            <span className={cn("text-xs", m.month === now ? "font-medium" : "text-muted-foreground")}>{monthName(m.month)}</span>
            <span className="sr-only">{money(s.budget.currency, m.spent)}</span>
          </li>
        ))}
      </ol>
    </Section>
  );
}

function Categories({ s }: { s: SpendingSummary }) {
  const top = Math.max(...s.byCategory.map((c) => c.spent), 1);
  return (
    <Section title="This month by category">
      {s.byCategory.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing in {s.budget.currency} this month.</p>
      ) : (
        <ul className="space-y-3">
          {s.byCategory.map((c) => (
            <li key={c.category} title={`${c.label}: ${money(s.budget.currency, c.spent)}`}>
              <div className="flex justify-between text-sm"><span>{c.label}</span><span className="tabular-nums text-muted-foreground">{money(s.budget.currency, c.spent)}</span></div>
              <div className="mt-1.5 h-2 rounded-full bg-muted"><div className="h-full rounded-full bg-foreground/40" style={{ width: `${(c.spent / top) * 100}%` }} /></div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function SpendList({ spends }: { spends: Spend[] }) {
  const remove = useRemoveSpend();
  const [confirming, setConfirming] = useState<string | null>(null);
  return (
    <ul className="divide-y overflow-hidden rounded-xl border bg-card" aria-label="Spends">
      {spends.map((sp) => (
        <li key={sp.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3">
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[15px] font-medium">{sp.vendor}</span>
            <span className="block truncate text-xs text-muted-foreground">
              {date(sp.paidOn)} · {sp.categoryLabel}
              {sp.source && <> · <Link href={`/l2/library?doc=${sp.source.documentId}`} className="text-primary hover:underline">receipt</Link></>}
            </span>
          </span>
          <span className="text-[15px] tabular-nums">{money(sp.currency, sp.amount)}</span>
          {confirming === sp.id ? (
            <span className="flex gap-1">
              <Button size="sm" variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate(sp.id, { onSuccess: () => setConfirming(null) })}>Remove</Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>Keep</Button>
            </span>
          ) : (
            <Button size="sm" variant="ghost" className="text-muted-foreground" onClick={() => setConfirming(sp.id)} aria-label={`Remove ${sp.vendor} spend`}>Remove</Button>
          )}
        </li>
      ))}
    </ul>
  );
}

function Empty({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed px-6 py-16 text-center">
      <Receipt className="size-7 text-muted-foreground" aria-hidden />
      <div>
        <p className="text-[15px] font-medium">No spending yet</p>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">Add a receipt or invoice in Lisena and it shows here, counted against the budget.</p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        <Button asChild><Link href="/l1/ask">Add a receipt in Lisena</Link></Button>
        <Button variant="outline" onClick={onAdd}>Add a spend by hand</Button>
      </div>
    </div>
  );
}

function AddSpend({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const add = useAddSpend();
  const blank = { vendor: "", amount: "", currency: "USD", category: "software", repeats: "once", paid_on: "" };
  const [form, setForm] = useState(blank);
  const set = (key: keyof typeof blank) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });
  const close = () => { setForm(blank); add.reset(); onOpenChange(false); };
  const ready = form.vendor.trim() && Number(form.amount) > 0;
  const select = "h-9 w-full rounded-md border bg-transparent px-3 text-[15px] outline-none focus-visible:ring-4 focus-visible:ring-ring/40";
  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add a spend</DialogTitle>
          <DialogDescription>For a payment with no receipt to upload. Receipts are better added in Lisena.</DialogDescription>
        </DialogHeader>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (ready) add.mutate({ ...form, vendor: form.vendor.trim(), ...(form.paid_on ? {} : { paid_on: undefined }) }, { onSuccess: close }); }}>
          <Field id="sp-vendor" label="Paid to"><Input id="sp-vendor" autoFocus value={form.vendor} onChange={set("vendor")} placeholder="Figma" /></Field>
          <div className="grid grid-cols-[1fr_7rem] gap-3">
            <Field id="sp-amount" label="Amount"><Input id="sp-amount" inputMode="decimal" value={form.amount} onChange={set("amount")} placeholder="15.00" /></Field>
            <Field id="sp-currency" label="Currency"><select id="sp-currency" className={select} value={form.currency} onChange={set("currency")}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
          </div>
          <Field id="sp-category" label="For"><select id="sp-category" className={select} value={form.category} onChange={set("category")}>{Object.entries(CATEGORIES).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field id="sp-repeats" label="Repeats"><select id="sp-repeats" className={select} value={form.repeats} onChange={set("repeats")}>{Object.entries(REPEATS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></Field>
            <Field id="sp-date" label="Paid on (optional)"><Input id="sp-date" type="date" value={form.paid_on} onChange={set("paid_on")} /></Field>
          </div>
          {add.isError && <p role="alert" className="text-sm text-risk">It could not be added. Check the amount and try again.</p>}
          <div className="flex justify-between gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={close}>Cancel</Button>
            <Button type="submit" disabled={!ready || add.isPending}>Add spend</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
