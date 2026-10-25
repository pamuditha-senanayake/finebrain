"use client";

// desk-check.tsx: steps 4 and 5 of a connection. Test (reads only; writes are listed, never called) and Live (on or off,
// with what came in). Used by: desk.tsx. Uses: desk-steps.tsx (Footer, Lead), lib/api/connections.ts.
import { Check, CircleSlash, X } from "lucide-react";
import { toast } from "sonner";
import { Folded } from "@/components/brain/card-pager";
import { Switch } from "@/components/ui/switch";
import { type Connection, type TestLine, switchConnection, testConnection, useConnectionAction } from "@/lib/api/connections";
import { relTime } from "@/lib/format";
import type { Step } from "./desk";
import { Footer, Lead } from "./desk-steps";

function LineIcon({ ok }: { ok: boolean | null }) {
  if (ok === true) return <Check className="size-4 text-ok" aria-label="Passed" />;
  if (ok === false) return <X className="size-4 text-risk" aria-label="Failed" />;
  return <CircleSlash className="size-4 text-muted-foreground" aria-label="Not called" />;
}

function TestLines({ lines }: { lines: TestLine[] }) {
  return (
    <ul className="divide-y rounded-lg border">
      {lines.map((line) => (
        <li key={line.item} className="flex items-start gap-3 px-4 py-3">
          <span className="mt-0.5"><LineIcon ok={line.ok} /></span>
          <span className="w-32 shrink-0 text-[15px] font-medium">{line.item}</span>
          <span className="min-w-0 text-[13px] text-muted-foreground">{line.detail}</span>
        </li>
      ))}
    </ul>
  );
}

export function TestStep({ connection, go }: { connection: Connection; go: (s: Step) => void }) {
  const test = useConnectionAction(() => testConnection(connection.id));
  const passed = connection.status === "tested" || connection.status === "live" || connection.status === "paused";
  const run = () => test.mutate(undefined);
  return (
    <div className="space-y-5">
      <Lead>The brain calls each part with the key and reads the answers. Anything that changes data is only listed.</Lead>
      {connection.tests.length > 0 && <TestLines lines={connection.tests} />}
      <Footer
        back="Answer"
        onBack={() => go("Answer")}
        next={test.isPending ? "Testing" : passed ? "Next: switch on" : connection.tests.length ? "Test again" : "Run the test"}
        onNext={passed ? () => go("Live") : run}
        nextDisabled={test.isPending}
      />
    </div>
  );
}

export function LiveStep({ connection, go }: { connection: Connection; go: (s: Step) => void }) {
  const live = useConnectionAction((on: boolean) => switchConnection(connection.id, on));
  const on = connection.status === "live";
  const ready = on || connection.status === "paused" || connection.status === "tested";
  const flip = (v: boolean) => live.mutate(v, { onError: (e) => toast.error(e.message === "test_first" ? "Pass the test first" : e.message === "not_allowed" ? "Only an L1 can switch it on" : e.message) });
  return (
    <div className="space-y-5">
      <label className="flex items-center gap-3 text-[15px]">
        <Switch checked={on} disabled={!ready || live.isPending} onCheckedChange={flip} />
        {on ? (connection.kind === "database" ? "On: agents may read" : "On: the brain is connected") : ready ? "Off" : "Pass the test first"}
      </label>
      {connection.kind === "database" && connection.tables.length > 0 && (
        <Folded title={`${connection.tables.length} tables readable`}>
          <ul className="space-y-1 text-[13px] text-muted-foreground">{connection.tables.map((t) => <li key={t}>{t}</li>)}</ul>
        </Folded>
      )}
      {on && connection.kind !== "database" && (
        <p className="text-[15px]">
          <span className="font-semibold tabular">{connection.events}</span>{" "}
          <span className="text-muted-foreground">items in · last {connection.lastEventAt ? relTime(connection.lastEventAt) : "none yet"}</span>
        </p>
      )}
      {connection.lastError && <p className="text-[13px] text-risk">Last problem: {connection.lastError}</p>}
      <Footer back="Test" onBack={() => go("Test")} />
    </div>
  );
}
