// One quiet line under the sources: where the brain searched for this answer (step 13b).
import type { AskAnswer } from "@/contracts";

type LookedIn = NonNullable<AskAnswer["lookedIn"]>;

const domainName = (id: string) => (id.charAt(0).toUpperCase() + id.slice(1)).replace(/_/g, " ");

/** "Looked in: 2 linked things · Customer care", "Looked in: Finance", or "Looked in: everything". */
export function lookedInLabel(scope: LookedIn): string {
  const domains = scope.domains.map(domainName).join(", ");
  if (scope.level === "tenant") return "Looked in: everything";
  if (scope.level === "domain") return `Looked in: ${domains}`;
  const things = `${scope.entityCount} linked ${scope.entityCount === 1 ? "thing" : "things"}`;
  return `Looked in: ${domains ? `${things} · ${domains}` : things}`;
}
