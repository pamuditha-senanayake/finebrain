"use client";

import { Brain, CheckCircle2, Database, Hand, KeyRound, ShieldAlert, ShieldCheck, Wrench, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { TraceStep } from "@/contracts";
import { Badge } from "@/components/ui/badge";
import { Beam } from "@/components/brain/motion";
import { AgentChip, useLookup } from "@/components/brain/names";
import { CritBadge, EnvBadge, KeyValue, Mono, PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useRun } from "@/lib/api/hooks";
import { date, dateTime, duration, num, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

const KIND: Record<TraceStep["kind"], { label: string; icon: typeof Brain; className: string; nature: string }> = {
  judgment: { label: "Model judgment", icon: Brain, className: "text-agent bg-agent/10", nature: "judgment" },
  tool: { label: "Tool call", icon: Wrench, className: "text-ok bg-ok/10", nature: "deterministic" },
  retrieval: { label: "Retrieval", icon: Database, className: "text-primary bg-primary/10", nature: "deterministic" },
  access_check: { label: "Access check", icon: KeyRound, className: "text-crit-1 bg-crit-1/10", nature: "deterministic" },
  quality_gate: { label: "Quality gate", icon: ShieldCheck, className: "text-warn-fg bg-warn/10", nature: "deterministic" },
  human: { label: "Human", icon: Hand, className: "text-env-production bg-env-production/10", nature: "human" },
};

export function RunTrace() {
  const { id } = useParams<{ id: string }>();
  const run = useRun(id);
  const lookup = useLookup();
  return (
    <QueryView query={run}>
      {(r) => {
        const totalTokens = r.steps.reduce((s, x) => s + x.costTokens, 0);
        return (
          <div>
            <PageHeader
              eyebrow={<span className="flex items-center gap-2"><Link href="/l3" className="hover:underline">Fleet</Link> / <AgentChip id={r.agentId} /></span>}
              title={r.subject}
              actions={
                <div className="flex items-center gap-2">
                  <EnvBadge env={r.env} />
                  <Status value={r.status} />
                </div>
              }
            />
            <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
              <Section title="Step timeline" description="Every step is labelled as model judgment or a deterministic call.">
                <Beam active={r.status === "running"} className="rounded-xl">
                  <ol className="relative space-y-3 border-l pl-5" aria-label="Trace steps">
                    {r.steps.map((s) => {
                      const k = KIND[s.kind];
                      const failed = s.decision === "deny" || s.decision === "fail" || s.decision === "error";
                      return (
                        <li key={s.id} className="relative">
                          <span className={cn("absolute -left-[31px] top-0.5 grid size-5 place-items-center rounded-full ring-4 ring-card", k.className)} aria-hidden>
                            <k.icon className="size-3" />
                          </span>
                          <div className="rounded-lg border bg-surface/60 p-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-medium">{s.title}</span>
                              <StatusChip tone={k.nature === "judgment" ? "agent" : k.nature === "human" ? "warn" : "neutral"}>{k.nature}</StatusChip>
                              <span className={cn("ml-auto inline-flex items-center gap-1 text-xs font-medium", failed ? "text-risk" : "text-ok")}>
                                {failed ? <XCircle className="size-3.5" /> : <CheckCircle2 className="size-3.5" />}
                                {s.decision}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-muted-foreground">{s.reason}</p>
                            {s.facts.length > 0 && (
                              <ul className="mt-2 space-y-1">
                                {s.facts.map((f) => (
                                  <li key={f.id} className="flex flex-wrap items-baseline gap-x-2 text-xs">
                                    <Link href={`/l2/vault?fact=${f.id}`} className="hover:underline">{f.statement}</Link>
                                    <span className="text-muted-foreground">valid {date(f.validFrom, lookup.tz)} → {f.validTo ? date(f.validTo, lookup.tz) : "now"}</span>
                                  </li>
                                ))}
                              </ul>
                            )}
                            {s.access && (
                              <div className={cn("mt-2 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs", s.access.decision === "deny" ? "bg-risk/10 text-risk" : "bg-ok/10 text-ok")}>
                                {s.access.decision === "deny" ? <ShieldAlert className="size-3.5" /> : <ShieldCheck className="size-3.5" />}
                                <Mono>{s.access.action}</Mono> · {s.access.decision} · rule <Mono>{s.access.ruleId}</Mono>
                              </div>
                            )}
                            {s.gate && <div className="mt-2 text-xs">Gate <Mono>{s.gate.name}</Mono>: {s.gate.passed ? <span className="text-ok">passed</span> : <span className="text-risk">failed</span>}</div>}
                            {s.tool && <div className="mt-2 text-xs">Tool <Mono className="rounded bg-muted px-1">{s.tool.replace("tool:", "")}</Mono></div>}
                            {s.templateFields.length > 0 && (
                              <div className="mt-2 text-xs">
                                Filled{" "}
                                {s.templateFields.map((f) => (
                                  <Mono key={f.field} className="rounded bg-muted px-1">{f.template}.{f.field} = {f.value}</Mono>
                                ))}
                              </div>
                            )}
                            <div className="mt-2 flex gap-3 text-[11px] text-muted-foreground">
                              <span>{dateTime(s.at, lookup.tz)}</span>
                              <span>{duration(s.durationMs)}</span>
                              {s.costTokens > 0 && <span>{num(s.costTokens)} tokens</span>}
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                </Beam>
              </Section>
              <div className="space-y-4">
                <Section title="Run">
                  <KeyValue
                    items={[
                      ["Run id", <Mono key="id">{r.id}</Mono>],
                      ["Agent", <AgentChip key="a" id={r.agentId} />],
                      ["Skill", <Link key="s" href={`/l2/skills/${r.skill.id}`} className="hover:underline"><Mono>{r.skill.id} v{r.skill.version} @ {r.skill.branch}</Mono></Link>],
                      ["Cluster", lookup.cluster(r.clusterId)],
                      ["Started", dateTime(r.startedAt, lookup.tz)],
                      ["Latency", duration(r.latencyMs)],
                      ["Cost", `${usd(r.costUsd)} · ${num(totalTokens || r.costTokens)} tokens`],
                      ["Human touch", r.humanTouch ? "yes" : "no"],
                    ]}
                  />
                </Section>
                {r.escalation && (
                  <Section title="Escalation" description="Why the agent stopped">
                    <div className="mb-2 flex items-center gap-2">
                      <CritBadge level={r.escalation.criticality} />
                      <Badge variant="outline">risk {r.escalation.risk}</Badge>
                    </div>
                    <p className="text-sm">{r.escalation.reason}</p>
                    {r.conversationId && (
                      <Link href={`/l3/conversations/${r.conversationId}`} className="mt-3 inline-block text-sm text-primary hover:underline">
                        Open the conversation
                      </Link>
                    )}
                  </Section>
                )}
                {r.failureClass && (
                  <Section title="Failure class">
                    <StatusChip tone="risk">{r.failureClass}</StatusChip>
                  </Section>
                )}
              </div>
            </div>
          </div>
        );
      }}
    </QueryView>
  );
}
