"use client";

// desk-steps.tsx: steps 1 to 3 of a connection. Describe (what the guide understood), Brief (copy the request for the
// other side's coding agent), Answer (paste that agent's whole answer back). Used by: desk.tsx. Uses: lib/api/connections.ts.
import { ArrowLeft, ArrowRight, Check, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Folded } from "@/components/brain/card-pager";
import { StatusChip } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { type Connection, DeliveryProblems, deliverConnection, useBrief, useConnectionAction } from "@/lib/api/connections";
import type { Step } from "./desk";

export const Lead = ({ children }: { children: React.ReactNode }) => <p className="text-[15px] leading-relaxed text-muted-foreground">{children}</p>;

/** Back on the left, the next step on the right: the way forward is always at the bottom. */
export function Footer({ back, next, onBack, onNext, nextDisabled }: { back?: Step; next?: string; onBack?: () => void; onNext?: () => void; nextDisabled?: boolean }) {
  return (
    <div className="flex items-center justify-between border-t pt-5">
      {back ? <Button variant="ghost" onClick={onBack}><ArrowLeft /> {back}</Button> : <span />}
      {next && <Button onClick={onNext} disabled={nextDisabled}>{next} <ArrowRight /></Button>}
    </div>
  );
}

export function DescribeStep({ connection, go }: { connection: Connection | null; go: (s: Step) => void }) {
  if (!connection || connection.needs.length === 0) {
    return <Lead>Tell the guide what you want to connect and what the brain should do with it. It writes the request for you.</Lead>;
  }
  return (
    <div className="space-y-5">
      <Lead>{connection.goal}</Lead>
      <ul className="divide-y rounded-lg border">
        {connection.needs.map((need) => (
          <li key={need.name} className="flex items-start gap-3 px-4 py-3">
            <span className="w-32 shrink-0 text-[15px] font-medium">{need.label}</span>
            <span className="min-w-0 flex-1 text-[13px] text-muted-foreground">{need.text}</span>
            {need.writes && <StatusChip tone="warn">changes data</StatusChip>}
          </li>
        ))}
      </ul>
      <p className="text-[13px] text-muted-foreground">Not right? Tell the guide what to change.</p>
      <Footer next="Next: the request" onNext={() => go("Brief")} />
    </div>
  );
}

export function BriefStep({ connection, go }: { connection: Connection; go: (s: Step) => void }) {
  const brief = useBrief(connection.id);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(brief.data?.brief ?? "");
    setCopied(true);
    toast.success("Copied. Send it to whoever builds this system.");
  };
  return (
    <div className="space-y-5">
      <Lead>
        {connection.kind === "database"
          ? `Send this request to whoever runs ${connection.system || connection.name}. They create a user for the brain that can only read, and answer with its address. They can paste it into their coding agent.`
          : `Send this request to whoever builds ${connection.system || connection.name}. They paste it into their coding agent (Claude Code, Cursor or similar), which prepares the connection and answers with the settings and a key.`}
      </Lead>
      <Button size="lg" onClick={copy} disabled={!brief.data}>{copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy request for their coding agent"}</Button>
      <Folded title="Preview the request">
        <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-4 text-[13px] leading-relaxed">{brief.data?.brief ?? "Loading"}</pre>
      </Folded>
      <Footer back="Describe" onBack={() => go("Describe")} next="Next: paste their answer" onNext={() => go("Answer")} />
    </div>
  );
}

export function AnswerStep({ connection, go }: { connection: Connection; go: (s: Step) => void }) {
  const [answer, setAnswer] = useState("");
  const [problems, setProblems] = useState<string[]>([]);
  const deliver = useConnectionAction((text: string) => deliverConnection(connection.id, { answer: text }));
  const read = () => {
    setProblems([]);
    deliver.mutate(answer, {
      onSuccess: () => { setAnswer(""); go("Test"); },
      onError: (e) => setProblems(e instanceof DeliveryProblems ? [...e.problems, ...(e.keysKept.length ? ["The key was found and kept; only the settings need fixing."] : [])] : [e.message]),
    });
  };
  return (
    <div className="space-y-5">
      <Lead>Paste their coding agent&apos;s whole answer. The brain picks out the settings and the key, and keeps the key encrypted.</Lead>
      <Textarea value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Paste the whole answer here" aria-label="Their answer" className="min-h-48 text-[13px]" />
      {problems.length > 0 && (
        <ul className="space-y-1 rounded-lg bg-risk/10 p-4 text-[13px] text-risk" aria-live="polite">
          {problems.map((p) => <li key={p}>{p}</li>)}
        </ul>
      )}
      {connection.secretsSet.length > 0 && <p className="text-[13px] text-muted-foreground">Already kept: {connection.secretsSet.map((s) => (s === "api_key" ? "API key" : "push secret")).join(", ")}</p>}
      <Footer back="Brief" onBack={() => go("Brief")} next={deliver.isPending ? "Reading" : "Read answer"} onNext={read} nextDisabled={!answer.trim() || deliver.isPending} />
    </div>
  );
}
