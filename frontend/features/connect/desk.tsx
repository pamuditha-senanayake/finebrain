"use client";

// desk.tsx: one connection. The guide chat sits on the left; the card on the right shows only the step the
// connection is on: 1 Describe, 2 Brief, 3 Answer, 4 Test, 5 Live. Used by: connections-page.tsx.
// Uses: desk-guide.tsx, desk-steps.tsx, desk-check.tsx, lib/api/connections.ts.
import { ArrowLeft, Check } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader, StatusChip } from "@/components/brain/primitives";
import { type Connection, type Kind, useConnections } from "@/lib/api/connections";
import { cn } from "@/lib/utils";
import { LiveStep, TestStep } from "./desk-check";
import { GuideChat } from "./desk-guide";
import { AnswerStep, BriefStep, DescribeStep } from "./desk-steps";

export const STEPS = ["Describe", "Brief", "Answer", "Test", "Live"] as const;
export type Step = (typeof STEPS)[number];
const TONE = { waiting: "neutral", delivered: "info", tested: "info", live: "ok", paused: "warn" } as const;

/** The step a connection is on, from what it has. */
function stepOf(c: Connection | null): Step {
  if (!c || c.needs.length === 0) return "Describe";
  if (c.status === "waiting") return "Brief";
  return c.status === "delivered" ? "Test" : "Live";
}

/** A numbered line of steps. It shows where you are; it is not a set of buttons. */
function StepLine({ at }: { at: Step }) {
  const reached = STEPS.indexOf(at);
  return (
    <ol className="flex items-center" aria-label={`Step ${reached + 1} of ${STEPS.length}: ${at}`}>
      {STEPS.map((step, i) => (
        <li key={step} className="flex flex-1 items-center last:flex-none" aria-current={i === reached ? "step" : undefined}>
          <span className="flex flex-col items-center gap-1.5">
            <span className={cn("flex size-7 items-center justify-center rounded-full text-[13px] font-medium",
              i < reached && "bg-ok/15 text-ok", i === reached && "bg-primary text-primary-foreground", i > reached && "border text-muted-foreground")}>
              {i < reached ? <Check className="size-3.5" aria-hidden /> : i + 1}
            </span>
            <span className={cn("text-[12px]", i === reached ? "font-medium text-foreground" : "text-muted-foreground")}>{step}</span>
          </span>
          {i < STEPS.length - 1 && <span className={cn("mx-2 mb-5 h-px flex-1", i < reached ? "bg-ok/40" : "bg-border")} aria-hidden />}
        </li>
      ))}
    </ol>
  );
}

function StepCard({ connection }: { connection: Connection | null }) {
  const [picked, setPicked] = useState<Step | null>(null);
  const step = picked ?? stepOf(connection);
  const go = (s: Step) => setPicked(s);
  return (
    <article className="min-w-0 space-y-8 rounded-xl border bg-card p-6 sm:p-8">
      <header className="flex items-start justify-between gap-3">
        <p className="min-w-0 truncate text-[13px] text-muted-foreground">{connection?.system || "Describe it to the guide"}</p>
        {connection && <StatusChip tone={TONE[connection.status]}>{connection.status}</StatusChip>}
      </header>
      <StepLine at={step} />
      {step === "Describe" && <DescribeStep connection={connection} go={go} />}
      {connection && step === "Brief" && <BriefStep connection={connection} go={go} />}
      {connection && step === "Answer" && <AnswerStep connection={connection} go={go} />}
      {connection && step === "Test" && <TestStep connection={connection} go={go} />}
      {connection && step === "Live" && <LiveStep connection={connection} go={go} />}
    </article>
  );
}

/** One connection: the guide on the left, its current step on the right. A new one starts from the chosen type and platform. */
export function ConnectionDesk({ connectionId, start }: { connectionId: string | null; start?: { kind: Kind; platform: string; prompt: string; from?: string } }) {
  const router = useRouter();
  const connections = useConnections();
  const current = connections.data?.find((c) => c.id === connectionId) ?? null;
  const platform = current?.platform || start?.platform || "";
  const drafted = (id: string) => router.replace(`/l2/connections?c=${id}`);
  return (
    <div className="space-y-6">
      <Link href="/l2/connections" className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Connections</Link>
      <PageHeader title={current?.name ?? "New connection"} description={platform || "Platform not named yet"} />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <GuideChat connection={current} start={start} onDrafted={drafted} />
        <StepCard key={`${current?.id ?? "new"}:${current?.status ?? ""}:${current?.needs.length ?? 0}`} connection={current} />
      </div>
    </div>
  );
}
