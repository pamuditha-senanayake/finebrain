"use client";

// The Lab: two actions (upload a pack, start an experiment), then the packs and runs it holds. An upload shows every audit;
// a failing one says which lines to fix, and each warning asks for a typed reason before the pack is kept.
import { ArrowLeft, FileUp, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { LabAudit } from "@/contracts/research";
import { EmptyState, PageHeader, QueryView, Section, Status, StatusChip, type Tone } from "@/components/brain/primitives";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useExperiments, usePacks, useUploadPack, type UploadAnswer } from "./lab-api";
import { LabGate, paperLabel } from "./lab-ui";

const AUDIT_TONE: Record<LabAudit["status"], Tone> = { pass: "ok", warn: "warn", fail: "risk", not_applicable: "neutral" };

export function ResearchLab() {
  const [uploading, setUploading] = useState(false);
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        eyebrow={<Link href="/research" className="inline-flex items-center gap-1 hover:text-foreground"><ArrowLeft className="size-3" /> Research</Link>}
        title="Lab"
        description="Runs the real Finebrain pipeline on a pack, in a tenant of its own that nothing else sees."
        actions={
          <>
            <Button variant="outline" onClick={() => setUploading(true)}><FileUp /> Upload pack</Button>
            <Button asChild><Link href="/research/lab/new"><Plus /> New experiment</Link></Button>
          </>
        }
      />
      <LabGate>
        <div className="space-y-6">
          <Runs />
          <Packs onUpload={() => setUploading(true)} />
        </div>
        <UploadDialog open={uploading} onOpenChange={setUploading} />
      </LabGate>
    </div>
  );
}

function Runs() {
  const experiments = useExperiments();
  return (
    <Section title="Runs">
      <QueryView query={experiments} rows={3} empty={<EmptyState title="No runs yet" description="Upload a pack and lock a preregistration, then start an experiment." />}>
        {(rows) => (
          <ul className="divide-y">
            {rows.map((e) => (
              <li key={e.id}>
                <Link href={`/research/lab/${e.id}`} className="flex items-center justify-between gap-4 py-3 text-[15px] hover:text-foreground">
                  <span>{paperLabel(e.paper)} · {e.conditions.join(", ")}</span>
                  <span className="flex items-center gap-3"><span className="tabular text-muted-foreground">${(e.costUsd ?? 0).toFixed(2)}</span><Status value={e.status} /></span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </QueryView>
    </Section>
  );
}

function Packs({ onUpload }: { onUpload: () => void }) {
  const packs = usePacks();
  return (
    <Section title="Packs">
      <QueryView query={packs} rows={3} empty={<EmptyState title="No packs yet" description="A pack holds the documents, questions and gold answers a run uses." action={<Button size="sm" variant="outline" onClick={onUpload}><FileUp /> Upload pack</Button>} />}>
        {(rows) => (
          <ul className="divide-y">
            {rows.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-4 py-3 text-[15px]">
                <span>{p.name} <span className="text-muted-foreground">v{p.version} · {p.kind}</span></span>
                <StatusChip tone={AUDIT_TONE[p.audit.verdict]}>{p.audit.verdict === "warn" ? "passed with reasons" : p.audit.verdict}</StatusChip>
              </li>
            ))}
          </ul>
        )}
      </QueryView>
    </Section>
  );
}

function UploadDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const upload = useUploadPack();
  const [file, setFile] = useState<File | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const answer: UploadAnswer | undefined = upload.data;
  const close = (next: boolean) => { if (!next) { setFile(null); setReasons({}); upload.reset(); } onOpenChange(next); };
  const send = (chosen: File | null) => chosen && upload.mutate({ file: chosen, reasons });

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Upload pack</DialogTitle>
          <DialogDescription>A zip with a manifest, documents, questions and gold answers. Ten checks run before it is kept.</DialogDescription>
        </DialogHeader>
        {!answer?.kept && (
          <div className="space-y-2">
            <Label htmlFor="pack-file">Pack file</Label>
            <Input id="pack-file" type="file" accept=".zip,application/zip" onChange={(e) => { setFile(e.target.files?.[0] ?? null); upload.reset(); }} />
          </div>
        )}
        {upload.error && <p role="alert" className="text-[15px] text-risk">{(upload.error as Error).message}</p>}
        {answer?.kept && <p className="text-[15px]">{answer.created ? "Pack kept" : "This pack was already kept"}: {answer.pack.name} v{answer.pack.version}.</p>}
        {answer && !answer.kept && <Audits audits={answer.audits} needs={answer.needs} reasons={reasons} setReasons={setReasons} />}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => close(false)}>{answer?.kept ? "Done" : "Cancel"}</Button>
          {!answer?.kept && (
            <Button disabled={!file || upload.isPending || (answer?.needs ?? []).some((key) => !reasons[key]?.trim())} onClick={() => send(file)}>
              {upload.isPending ? "Checking…" : answer && !answer.kept && answer.needs.length ? "Keep with these reasons" : "Check and keep"}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Audits({ audits, needs, reasons, setReasons }: { audits: LabAudit[]; needs: string[]; reasons: Record<string, string>; setReasons: (r: Record<string, string>) => void }) {
  const failed = audits.some((a) => a.status === "fail");
  const passed = audits.filter((a) => a.status === "pass");
  return (
    <div className="space-y-2">
      <p className="text-[15px] font-medium">{failed ? "Not kept: fix the failing checks, then upload again." : "Each warning needs a reason before the pack is kept."}</p>
      <details className="text-[13px] text-muted-foreground">
        <summary className="cursor-pointer">{passed.length} checks passed</summary>
        <p className="mt-1">{passed.map((a) => a.label).join(", ")}.</p>
      </details>
      <ul className="divide-y rounded-xl border">
        {audits.filter((a) => a.status === "warn" || a.status === "fail").map((audit) => (
          <li key={audit.key} className="space-y-2 p-3">
            <div className="flex items-center justify-between gap-3 text-[15px]"><span>{audit.label}</span><StatusChip tone={AUDIT_TONE[audit.status]}>{audit.status}</StatusChip></div>
            <p className="text-[13px] text-muted-foreground">{audit.detail}</p>
            {audit.lines.length > 0 && (
              <details><summary className="cursor-pointer text-[13px]">Show {audit.lines.length} lines</summary>
                <ul className="mt-1 space-y-1 font-mono text-[12px]">{audit.lines.map((line) => <li key={line} className="break-words">{line}</li>)}</ul>
              </details>
            )}
            {needs.includes(audit.key) && (
              <Input aria-label={`Reason for ${audit.label}`} placeholder="Why this is acceptable" value={reasons[audit.key] ?? ""} onChange={(e) => setReasons({ ...reasons, [audit.key]: e.target.value })} />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
