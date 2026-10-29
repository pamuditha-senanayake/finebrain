"use client";

import { KeyRound, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import type { EvidenceRequest } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CommitButton } from "@/components/brain/motion";
import { useLookup } from "@/components/brain/names";
import { KeyValue } from "@/components/brain/primitives";
import { useOp, useTenantId } from "@/lib/api/hooks";
import { UPLOAD_TYPES, useUploadEvidence } from "@/lib/api/upload";
import { realTenants } from "@/lib/flags";

/** What can be done about one request: upload a document, or grant a data source instead. Used by evidence.tsx. */
export function RequestActions({ req }: { req: EvidenceRequest }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [grantOpen, setGrantOpen] = useState(false);
  const upload = useOp<{ requestId: string; fileName: string; sizeKb: number }>("uploadEvidence", { success: "Evidence filed" });
  const real = realTenants.has(useTenantId()); // HQ files the real file; its facts are then reviewed in the Vault
  const uploadFile = useUploadEvidence();
  if (req.status === "awaiting_grant_approval") {
    return (
      <p className="text-[15px] text-muted-foreground" data-testid={`evidence-${req.id}`}>
        Waiting for two L1 approvals. <Link href="/l1/digest?tab=approvals" className="text-primary hover:underline">Approvals</Link>
      </p>
    );
  }
  if (req.status !== "open") return null;
  return (
    <div className="flex flex-wrap gap-3" data-testid={`evidence-${req.id}`}>
      <input
        ref={fileRef}
        type="file"
        className="sr-only"
        accept={real ? UPLOAD_TYPES : undefined}
        aria-label={`Upload evidence for ${req.item}`}
        data-testid={`upload-${req.id}`}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f && real) uploadFile.mutate({ requestId: req.id, file: f });
          else if (f) upload.mutate({ requestId: req.id, fileName: f.name, sizeKb: f.size / 1024 });
        }}
      />
      <Button onClick={() => fileRef.current?.click()} disabled={upload.isPending || uploadFile.isPending}>
        <Upload /> Upload
      </Button>
      {req.suggestedGrant && (
        <Button variant="outline" onClick={() => setGrantOpen(true)}>
          <KeyRound /> Grant a data source
        </Button>
      )}
      {req.suggestedGrant && <GrantDialog req={req} open={grantOpen} onOpenChange={setGrantOpen} />}
    </div>
  );
}

/** Shows exactly what would be granted before anything is. A grant is C4: two L1 leaders approve it. */
function GrantDialog({ req, open, onOpenChange }: { req: EvidenceRequest; open: boolean; onOpenChange: (open: boolean) => void }) {
  const lookup = useLookup();
  const grant = useOp<{ requestId: string }>("requestGrant", { success: "Grant requested. C4 needs two L1 approvals." });
  const g = req.suggestedGrant!;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Grant access: {g.source}</DialogTitle>
          <DialogDescription>Check exactly what you are granting before anything is granted.</DialogDescription>
        </DialogHeader>
        <KeyValue items={[["Scope", g.scope], ["Retention", `${g.retentionDays} days`], ["Agents that will use it", g.agents.map((a) => lookup.name(a)).join(", ")], ["How to revoke", g.revoke], ["Approval", "C4: two L1 approvers"]]} />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <CommitButton criticality={4} onClick={() => grant.mutate({ requestId: req.id }, { onSuccess: () => onOpenChange(false) })} disabled={grant.isPending}>
            <KeyRound /> Request grant
          </CommitButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
