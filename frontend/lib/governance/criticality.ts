import type { Criticality, Tier, Touches } from "@/contracts";

export const CRITICALITY_LABEL: Record<Criticality, string> = {
  0: "Routine",
  1: "Low",
  2: "Medium",
  3: "High",
  4: "Critical",
};

export type ChangeKind =
  | "log"
  | "template_refresh"
  | "faq_wording"
  | "resolver_synonym"
  | "skill_step_edit"
  | "website_copy"
  | "new_skill"
  | "new_policy"
  | "policy_change"
  | "refund_rule"
  | "pricing_page"
  | "ground_truth_change"
  | "new_data_scope"
  | "tax_signoff"
  | "security_role_change"
  | "inbox_access_grant"
  | "ground_truth_delete"
  | "capability_grant";

/** Base level per change kind, from the criticality table in section 7 of the brief. */
export const BASE_CRITICALITY: Record<ChangeKind, Criticality> = {
  log: 0,
  template_refresh: 0,
  faq_wording: 1,
  resolver_synonym: 1,
  skill_step_edit: 2,
  website_copy: 2,
  new_skill: 3,
  new_policy: 3,
  policy_change: 3,
  refund_rule: 3,
  pricing_page: 3,
  ground_truth_change: 3,
  new_data_scope: 3,
  tax_signoff: 4,
  security_role_change: 4,
  inbox_access_grant: 4,
  ground_truth_delete: 4,
  capability_grant: 4,
};

export type CriticalityResult = { level: Criticality; reasons: string[] };

/**
 * A change that touches money, personal data, public content, legal or tax matters,
 * or more than one cluster moves up one level. The bump applies once, capped at C4.
 *
 * C3 is already defined as "money, customers, public content or ground truth", so a C3 change
 * only moves to C4 when it reaches what C4 is for: legal or tax matters, personal data,
 * or more than one cluster. This keeps "any new skill" at C3 even when that skill handles money.
 */
export function assessCriticality(kind: ChangeKind, touches: Touches): CriticalityResult {
  const base = BASE_CRITICALITY[kind];
  const reasons = [`${kind.replaceAll("_", " ")} starts at C${base}`];
  const escalators: string[] = [];
  if (touches.money && base < 3) escalators.push("touches money");
  if (touches.personalData) escalators.push("touches personal data");
  if (touches.publicContent && base < 3) escalators.push("touches public content");
  if (touches.legalTax) escalators.push("touches legal or tax matters");
  if (touches.clusters.length > 1) escalators.push("spans more than one cluster");
  let level = base;
  if (escalators.length > 0 && base < 4) {
    level = (base + 1) as Criticality;
    reasons.push(`moves up one level because it ${escalators.join(", ")}`);
  }
  return { level, reasons };
}

export type ApproverRequirement = {
  automatic: boolean;
  tier: Tier;
  count: number;
  label: string;
  requiresBeforeApproval: string[];
};

export function approverFor(level: Criticality): ApproverRequirement {
  switch (level) {
    case 0:
      return { automatic: true, tier: "L2", count: 0, label: "Automatic and logged", requiresBeforeApproval: [] };
    case 1:
      return { automatic: true, tier: "L2", count: 0, label: "L2 supervisor agent, steward notified", requiresBeforeApproval: ["Passing tests"] };
    case 2:
      return { automatic: false, tier: "L2", count: 1, label: "L2 human steward", requiresBeforeApproval: ["Sandbox tests"] };
    case 3:
      return { automatic: false, tier: "L1", count: 1, label: "L1 DRI", requiresBeforeApproval: ["Impact preview", "Replay"] };
    case 4:
      return { automatic: false, tier: "L1", count: 2, label: "Two L1 approvers", requiresBeforeApproval: ["Impact preview", "Replay", "Optional cooling period"] };
  }
}

export type Voter = { id: string; tier: Tier; maxApprovalCriticality: Criticality };

/** Returns null when the voter may approve, or the reason they may not. */
export function canApprove(voter: Voter, level: Criticality, alreadyVoted: string[]): string | null {
  if (alreadyVoted.includes(voter.id)) return "You have already approved this. The two person rule needs a different approver.";
  if (level > voter.maxApprovalCriticality) {
    return `C${level} needs ${approverFor(level).label}. Your ceiling is C${voter.maxApprovalCriticality}.`;
  }
  if (level >= 3 && voter.tier !== "L1") return `C${level} needs an L1 approver.`;
  return null;
}

export function approvalsStillNeeded(level: Criticality, approvedBy: string[]): number {
  const req = approverFor(level);
  return Math.max(0, req.count - new Set(approvedBy).size);
}
