"use client";

import { FlaskConical, GitBranch, History, ShieldCheck, Telescope } from "lucide-react";
import Link from "next/link";
import type { ChangeRequest } from "@/contracts";
import { Badge } from "@/components/ui/badge";
import { approverFor } from "@/lib/governance/criticality";
import { cn } from "@/lib/utils";
import { CritBadge, EnvBadge, Mono, Section, Status, StatusChip } from "./primitives";

export function PlainDiff({ cr }: { cr: ChangeRequest }) {
  return (
    <ul className="space-y-1.5" aria-label="Plain language diff">
      {cr.plainDiff.map((line, i) => (
        <li key={i} className="flex gap-2 text-sm">
          <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
          <span>{line}</span>
        </li>
      ))}
    </ul>
  );
}

export function StructuredDiff({ cr }: { cr: ChangeRequest }) {
  return (
    <div className="overflow-x-auto">
      <table className="mini-table" aria-label="Structured diff">
        <thead className="text-left">
          <tr>
            <th className="px-2 py-1.5 text-left font-medium">Op</th>
            <th className="px-2 py-1.5 text-left font-medium">Node</th>
            <th className="px-2 py-1.5 text-left font-medium">Field</th>
            <th className="px-2 py-1.5 text-left font-medium">Before</th>
            <th className="px-2 py-1.5 text-left font-medium">After</th>
          </tr>
        </thead>
        <tbody>
          {cr.changes.map((c, i) => (
            <tr key={i} className="border-t align-top">
              <td className="px-2 py-1.5">
                <StatusChip tone={c.op === "add" ? "ok" : c.op === "remove" ? "risk" : "info"}>{c.op}</StatusChip>
              </td>
              <td className="px-2 py-1.5">
                <div className="font-medium">{c.label}</div>
                <Mono className="text-muted-foreground">{c.nodeType}:{c.nodeId}</Mono>
              </td>
              <td className="px-2 py-1.5"><Mono>{c.field ?? "·"}</Mono></td>
              <td className="px-2 py-1.5"><span className="rounded bg-risk/10 px-1 text-risk line-through decoration-risk/40">{c.before ?? "·"}</span></td>
              <td className="px-2 py-1.5"><span className="rounded bg-ok/10 px-1 text-ok">{c.after ?? "·"}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ImpactAndTests({ cr }: { cr: ChangeRequest }) {
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <div className={cn("rounded-lg border p-3", !cr.impactPreview && "border-dashed")}>
        <div className="mb-1 flex items-center gap-1.5 text-xs font-medium">
          <Telescope className="size-3.5" /> Impact preview and replay
        </div>
        {cr.impactPreview ? (
          <>
            <p className="text-sm" data-testid="impact-summary">{cr.impactPreview.summary}</p>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              {cr.impactPreview.runsReplayed > 0 && (
                <>
                  <Badge variant="secondary">{cr.impactPreview.runsReplayed.toLocaleString()} runs replayed</Badge>
                  <Badge variant="secondary">{cr.impactPreview.decisionsChanged} decisions change</Badge>
                </>
              )}
              <StatusChip tone={cr.impactPreview.predictedRisk === "high" ? "risk" : cr.impactPreview.predictedRisk === "medium" ? "warn" : "ok"}>risk {cr.impactPreview.predictedRisk}</StatusChip>
            </div>
            {cr.impactPreview.examples.map((ex) => (
              <div key={ex.runId} className="mt-2 rounded bg-surface p-2 text-xs">
                <Link href={`/l3/runs/${ex.runId}`} className="font-mono hover:underline">{ex.runId}</Link>: <span className="text-risk">{ex.before}</span> → <span className="text-ok">{ex.after}</span>
              </div>
            ))}
          </>
        ) : (
          <p className="text-xs text-muted-foreground">Not run yet. Nothing goes live blind: run the replay before asking for approval.</p>
        )}
      </div>
      <div className={cn("rounded-lg border p-3", !cr.tests && "border-dashed")}>
        <div className="mb-1 flex items-center gap-1.5 text-xs font-medium">
          <FlaskConical className="size-3.5" /> Sandbox tests
        </div>
        {cr.tests ? (
          <>
            <p className="text-sm">
              <span className={cn("font-semibold", cr.tests.failed ? "text-risk" : "text-ok")}>{cr.tests.passed} of {cr.tests.total} passed</span> in <Mono>{cr.tests.suite}</Mono>
            </p>
            {cr.tests.k > 1 && <p className="mt-1 text-xs text-muted-foreground">Consistency pass^{cr.tests.k}: {(cr.tests.passK * 100).toFixed(0)}%</p>}
          </>
        ) : (
          <p className="text-xs text-muted-foreground">Not run yet.</p>
        )}
      </div>
    </div>
  );
}

export function ChangeRequestSummary({ cr, compact = false }: { cr: ChangeRequest; compact?: boolean }) {
  const req = approverFor(cr.criticality);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <CritBadge level={cr.criticality} showLabel />
        <Status value={cr.status} />
        <span className="inline-flex items-center gap-1 text-muted-foreground">
          <GitBranch className="size-3.5" />
          <Mono>{cr.fromBranch}</Mono> → <Mono>{cr.toBranch}</Mono>
        </span>
        <EnvBadge env="sandbox" branch={cr.fromBranch} />
      </div>
      <Section title="What changes, in plain language">
        <PlainDiff cr={cr} />
      </Section>
      {!compact && (
        <Section title="Structured diff">
          <StructuredDiff cr={cr} />
        </Section>
      )}
      <ImpactAndTests cr={cr} />
      <Section title={<span className="flex items-center gap-1.5"><ShieldCheck className="size-3.5" /> Why this needs {req.label}</span>}>
        <ul className="space-y-1 text-xs text-muted-foreground">
          {cr.criticalityReasons.map((r) => (
            <li key={r}>· {r}</li>
          ))}
          <li>· Required before approval: {req.requiresBeforeApproval.join(", ") || "nothing"}</li>
        </ul>
      </Section>
      {cr.mergedAt && (
        <p className="flex items-center gap-1.5 text-xs text-ok">
          <History className="size-3.5" /> Merged to main. Live in Production.
        </p>
      )}
    </div>
  );
}
