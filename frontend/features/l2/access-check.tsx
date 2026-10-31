"use client";

import { useMutation } from "@tanstack/react-query";
import { Check, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Mono } from "@/components/brain/primitives";
import { AccessCheckResult } from "@/contracts";
import { useAgents, useHumans, useStudioOptions } from "@/lib/api/hooks";
import { apiPost } from "@/lib/api/client";
import { reportError } from "@/lib/errors";

// Config
const SENSITIVITY = [["public", "Public"], ["internal", "Internal"], ["confidential", "Confidential"], ["restricted", "Restricted"]] as const;
const ITSELF = "itself";
/** Each access rule in plain words. Also used by the Living memory's trace page. */
export const RULE_WORDS: Record<string, string> = {
  missing_capability: "This agent has not been given that capability",
  sensitivity_by_tier: "This data is too sensitive for the agent's tier",
  on_behalf_of: "The person it works for may not see this data",
  capability_and_tier: "The agent holds the capability and may read this data",
  opa_unreachable: "The access service did not answer, so the answer is no",
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label className="text-[14px]">{label}</Label>{children}</div>;
}

/** "Would this be allowed?" Runs the real access rules on a made-up action. Nothing runs and nothing is logged. */
export function AccessCheckDialog({ open, onOpenChange, agentId }: { open: boolean; onOpenChange: (open: boolean) => void; agentId?: string }) {
  const agents = useAgents().data ?? [];
  const humans = useHumans().data ?? [];
  const options = useStudioOptions().data?.capabilities ?? [];
  const [agent, setAgent] = useState(agentId ?? "");
  const [action, setAction] = useState("");
  const [sensitivity, setSensitivity] = useState("internal");
  const [person, setPerson] = useState(ITSELF);
  const chosen = agents.find((a) => a.id === (agent || agentId));
  const choices = [...new Set([...(chosen?.capabilities ?? []), ...options.map((o) => o.id)])];
  const check = useMutation({
    mutationFn: () => apiPost("ops/accessCheck", { agentId: chosen?.id, action, sensitivity, onBehalfOf: person === ITSELF ? null : person }, AccessCheckResult),
    onError: (e) => reportError(e, { op: "accessCheck" }),
  });
  const reset = (set: () => void) => { set(); check.reset(); };
  const label = (id: string) => options.find((o) => o.id === id)?.label ?? id;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md gap-6">
        <DialogHeader>
          <DialogTitle>Check access</DialogTitle>
          <DialogDescription>Pick an agent and an action. We run the real rules. Nothing is done.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="Agent">
            <Select value={chosen?.id ?? ""} onValueChange={(v) => reset(() => setAgent(v))}>
              <SelectTrigger className="w-full" aria-label="Agent"><SelectValue placeholder="Choose an agent" /></SelectTrigger>
              <SelectContent>{agents.map((a) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Action">
            <Select value={action} onValueChange={(v) => reset(() => setAction(v))}>
              <SelectTrigger className="w-full" aria-label="Action"><SelectValue placeholder="Choose an action" /></SelectTrigger>
              <SelectContent>{choices.map((c) => <SelectItem key={c} value={c}>{label(c)}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Data">
            <Select value={sensitivity} onValueChange={(v) => reset(() => setSensitivity(v))}>
              <SelectTrigger className="w-full" aria-label="Data sensitivity"><SelectValue /></SelectTrigger>
              <SelectContent>{SENSITIVITY.map(([id, name]) => <SelectItem key={id} value={id}>{name}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Working for">
            <Select value={person} onValueChange={(v) => reset(() => setPerson(v))}>
              <SelectTrigger className="w-full" aria-label="Working for"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ITSELF}>No one (itself)</SelectItem>
                {humans.map((h) => <SelectItem key={h.id} value={h.id}>{h.name} · {h.tier}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <div aria-live="polite">
          {check.data && (
            <div className={`flex gap-3 rounded-xl border p-4 ${check.data.allow ? "border-ok/40 bg-ok/5" : "border-risk/40 bg-risk/5"}`}>
              {check.data.allow ? <Check className="mt-0.5 size-5 shrink-0" aria-hidden /> : <X className="mt-0.5 size-5 shrink-0" aria-hidden />}
              <div className="space-y-1">
                <p className="text-[15px] font-medium">{check.data.allow ? "Allowed" : "Denied"}</p>
                <p className="text-[14px] text-muted-foreground">{RULE_WORDS[check.data.ruleId] ?? check.data.reason}. Acts as {check.data.effectiveTier}. <Mono>{check.data.ruleId}</Mono></p>
              </div>
            </div>
          )}
          {check.isError && <p className="text-[14px] text-risk">We could not run the check. Try again in a moment.</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          <Button disabled={!chosen || !action || check.isPending} onClick={() => check.mutate()}>
            <ShieldCheck /> {check.isPending ? "Checking" : "Check"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
