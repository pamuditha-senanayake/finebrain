"use client";

import { Crosshair, Download, Radar } from "lucide-react";
import { useMemo, useState } from "react";
import type { Sensor } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, type Column } from "@/components/brain/data-table";
import { useLookup } from "@/components/brain/names";
import { EmptyState, Mono, PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useAgents, useLoops, useOp, useSensors, useTrackingPlan } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { relTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export function Sensors() {
  const sensors = useSensors();
  const lookup = useLookup();
  const columns: Column<Sensor>[] = useMemo(
    () => [
      { id: "name", header: "Sensor", width: "minmax(180px,1.4fr)", value: (s) => s.name, cell: (s) => <span className="font-medium">{s.name}</span> },
      { id: "source", header: "Source", width: "minmax(140px,1fr)", value: (s) => s.source, hideOnMobile: true, cell: (s) => <span className="truncate text-muted-foreground">{s.source}</span> },
      { id: "cluster", header: "Cluster", width: "minmax(120px,1fr)", value: (s) => lookup.cluster(s.clusterId), hideOnMobile: true, cell: (s) => <span className="truncate text-muted-foreground">{lookup.cluster(s.clusterId)}</span> },
      { id: "health", header: "Health", width: "84px", value: (s) => s.health, cell: (s) => <Status value={s.health} /> },
      { id: "subs", header: "Subscribers", width: "minmax(120px,1fr)", value: (s) => s.subscribers.length, hideOnMobile: true, cell: (s) => <span className="truncate text-xs">{s.subscribers.map((x) => lookup.name(x)).join(", ") || "none"}</span> },
      { id: "scopes", header: "Scopes", width: "minmax(120px,1fr)", value: (s) => s.scopes.join(","), hideOnMobile: true, cell: (s) => <Mono className="truncate">{s.scopes.join(", ")}</Mono> },
      { id: "pd", header: "Personal data", width: "100px", value: (s) => (s.personalData ? 1 : 0), cell: (s) => (s.personalData ? <StatusChip tone="warn">yes, masked</StatusChip> : <span className="text-muted-foreground">no</span>) },
      { id: "retention", header: "Retention", width: "84px", align: "right", value: (s) => s.retentionDays, hideOnMobile: true, cell: (s) => `${s.retentionDays}d` },
      { id: "last", header: "Last event", width: "100px", value: (s) => s.lastEventAt, hideOnMobile: true, cell: (s) => <span className="text-muted-foreground">{relTime(s.lastEventAt)}</span> },
    ],
    [lookup],
  );
  return (
    <div>
      <PageHeader title="Sensors and connections" description="Every connected system per cluster with health, subscribers, scopes, retention and a personal data flag." />
      <Tabs defaultValue="sensors">
        <TabsList>
          <TabsTrigger value="sensors"><Radar /> Sensors</TabsTrigger>
          <TabsTrigger value="plant"><Crosshair /> Sensor planting</TabsTrigger>
        </TabsList>
        <TabsContent value="sensors" className="mt-3">
          <QueryView query={sensors}>{(ss) => <DataTable label="Sensors" data={ss} columns={columns} getRowId={(s) => s.id} initialSort={{ id: "health", desc: false }} height="calc(100dvh - 280px)" />}</QueryView>
        </TabsContent>
        <TabsContent value="plant" className="mt-3">
          <PlantingOverlay />
        </TabsContent>
      </Tabs>
    </div>
  );
}

const SITE_ELEMENTS = [
  { selector: "[data-track=nav-pricing]", label: "Navigation: Pricing link" },
  { selector: "[data-track=pricing-toggle]", label: "Pricing toggle (Monthly | Annual)" },
  { selector: "[data-track=plan-growth-cta]", label: "Growth plan: Start trial" },
  { selector: "[data-track=plan-scale-cta]", label: "Scale plan: Talk to sales" },
  { selector: "[data-track=faq-refunds]", label: "FAQ: Refund policy" },
  { selector: "[data-track=hero-cta]", label: "Hero call to action" },
];

function PlantingOverlay() {
  const plan = useTrackingPlan();
  const agents = useAgents();
  const loops = useLoops();
  const { user } = useCurrentUser();
  const [plant, setPlant] = useState(true);
  const [picked, setPicked] = useState<(typeof SITE_ELEMENTS)[number] | null>(null);
  const [eventName, setEventName] = useState("");
  const [props, setProps] = useState("page, plan");
  const [pd, setPd] = useState(false);
  const [mask, setMask] = useState(true);
  const [subs, setSubs] = useState<string[]>(["a-insights"]);
  const add = useOp<{ selector: string; elementLabel: string; eventName: string; properties: string[]; personalData: boolean; maskText: boolean; subscribers: string[] }>("addTrackingItem", { success: "Added to the tracking plan" });
  const tracked = new Set((plan.data ?? []).map((p) => p.selector));
  const pick = (el: (typeof SITE_ELEMENTS)[number]) => {
    if (!plant) return;
    setPicked(el);
    setEventName(el.selector.replace("[data-track=", "").replace("]", "").replaceAll("-", "_") + ".clicked");
  };
  const target = (sel: string, children: React.ReactNode, className?: string) => {
    const el = SITE_ELEMENTS.find((x) => x.selector === sel)!;
    return (
      <button
        type="button"
        onClick={() => pick(el)}
        className={cn("relative rounded-md outline-offset-2", plant && "hover:outline hover:outline-2 hover:outline-primary", picked?.selector === sel && "outline outline-2 outline-primary", className)}
        aria-label={plant ? `Attach a sensor to ${el.label}` : el.label}
      >
        {children}
        {tracked.has(sel) && <span className="absolute -right-2 -top-2 rounded-full bg-ok px-1.5 text-[9px] font-semibold text-white">tracked</span>}
      </button>
    );
  };
  const download = () => {
    const blob = new Blob([JSON.stringify(plan.data ?? [], null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "tracking-plan.json";
    a.click();
  };
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
      <Section
        title="finebase.lk preview"
        description="Click an element to attach a sensor. The output is a tracking plan, not a live integration."
        actions={
          <div className="flex items-center gap-2 text-xs">
            <Switch id="plant" checked={plant} onCheckedChange={setPlant} />
            <Label htmlFor="plant">Plant mode</Label>
          </div>
        }
      >
        <div className="overflow-hidden rounded-xl border bg-white text-slate-900 shadow-inner" aria-label="Website preview">
          <div className="flex items-center justify-between border-b px-4 py-2 text-sm">
            <span className="font-semibold">finebase</span>
            <nav className="flex gap-4 text-xs text-slate-600">
              <span>Product</span>
              {target("[data-track=nav-pricing]", <span className="text-xs">Pricing</span>)}
              <span>Services</span>
            </nav>
          </div>
          <div className="px-6 py-6 text-center">
            <h3 className="text-xl font-semibold">Plans that grow with you</h3>
            <div className="mt-3 inline-flex">
              {target("[data-track=pricing-toggle]", <span className="inline-flex rounded-full bg-slate-100 p-1 text-xs"><span className="rounded-full bg-white px-3 py-1 shadow">Monthly</span><span className="px-3 py-1">Annual (save 17%)</span></span>)}
            </div>
            <div className="mx-auto mt-5 grid max-w-xl gap-3 sm:grid-cols-2">
              <div className="rounded-xl border p-4 text-left">
                <div className="text-sm font-semibold">Growth</div>
                <div className="text-2xl font-bold">LKR 24,000<span className="text-xs font-normal">/mo (sample)</span></div>
                {target("[data-track=plan-growth-cta]", <span className="mt-3 block rounded-md bg-indigo-600 px-3 py-1.5 text-xs text-white">Start trial</span>, "mt-3 w-full")}
              </div>
              <div className="rounded-xl border p-4 text-left">
                <div className="text-sm font-semibold">Scale</div>
                <div className="text-2xl font-bold">Custom</div>
                {target("[data-track=plan-scale-cta]", <span className="mt-3 block rounded-md border px-3 py-1.5 text-xs">Talk to sales</span>, "mt-3 w-full")}
              </div>
            </div>
            <div className="mx-auto mt-5 max-w-xl text-left text-xs">
              {target("[data-track=faq-refunds]", <span className="block rounded-md border px-3 py-2">How do refunds work?</span>, "w-full")}
            </div>
          </div>
        </div>
      </Section>
      <div className="space-y-4">
        <Section title={picked ? `Attach a sensor: ${picked.label}` : "Pick an element"}>
          {picked ? (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                add.mutate({ selector: picked.selector, elementLabel: picked.label, eventName, properties: props.split(",").map((s) => s.trim()).filter(Boolean), personalData: pd, maskText: mask, subscribers: subs }, { onSuccess: () => setPicked(null) });
              }}
            >
              <div>
                <Label htmlFor="ev" className="text-xs">Event name</Label>
                <Input id="ev" value={eventName} onChange={(e) => setEventName(e.target.value)} className="mt-1 font-mono text-xs" />
              </div>
              <div>
                <Label htmlFor="props" className="text-xs">Properties (comma separated)</Label>
                <Input id="props" value={props} onChange={(e) => setProps(e.target.value)} className="mt-1 text-xs" />
              </div>
              <div className="flex flex-wrap gap-4 text-xs">
                <label className="flex items-center gap-1.5"><Checkbox checked={pd} onCheckedChange={(v) => setPd(!!v)} /> Captures personal data</label>
                <label className="flex items-center gap-1.5"><Checkbox checked={mask} onCheckedChange={(v) => setMask(!!v)} /> Mask element text</label>
              </div>
              <fieldset>
                <legend className="mb-1 text-xs">Subscribers</legend>
                <div className="max-h-36 space-y-1 overflow-auto text-xs">
                  {[...(loops.data ?? []).map((l) => ({ id: l.id, name: `Loop: ${l.name}` })), ...(agents.data ?? []).filter((a) => a.kind === "worker").map((a) => ({ id: a.id, name: a.name }))].slice(0, 60).map((s) => (
                    <label key={s.id} className="flex items-center gap-1.5">
                      <Checkbox checked={subs.includes(s.id)} onCheckedChange={(v) => setSubs((x) => (v ? [...x, s.id] : x.filter((y) => y !== s.id)))} />
                      {s.name}
                    </label>
                  ))}
                </div>
              </fieldset>
              <Button type="submit" size="sm" disabled={add.isPending || !user || user.tier === "L3"}>Add to tracking plan</Button>
            </form>
          ) : (
            <p className="text-xs text-muted-foreground">Turn on plant mode and click any highlighted element in the preview.</p>
          )}
        </Section>
        <Section title="Tracking plan" actions={<Button size="xs" variant="outline" onClick={download}><Download /> JSON</Button>}>
          <QueryView query={plan} rows={2} empty={<EmptyState title="Nothing planted yet" />}>
            {(items) => (
              <ul className="space-y-2 text-xs" data-testid="tracking-plan">
                {items.map((p) => (
                  <li key={p.id} className="rounded-lg border p-2">
                    <Mono className="font-medium">{p.eventName}</Mono>
                    <div className="text-muted-foreground">{p.elementLabel} · {p.properties.join(", ")}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {p.privacy.personalData && <StatusChip tone="warn">personal data</StatusChip>}
                      {p.privacy.maskText && <StatusChip tone="neutral">text masked</StatusChip>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </Section>
      </div>
    </div>
  );
}
