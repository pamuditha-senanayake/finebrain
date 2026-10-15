// Which parts handle a story scenario. Read by the chat engine and the parts pane.
import type { Scenario, StudioItem } from "@/contracts";

/** Parts linked to the scenario, plus any part named after it (the chat names new parts after the case they build). */
export function coverageOf(sc: Scenario, items: StudioItem[]): StudioItem[] {
  const title = sc.title.toLowerCase();
  return items.filter((i) => sc.coveredBy.includes(i.id) || i.name.toLowerCase() === title);
}

/** The prompt that builds a case: a skill named after it, doing what the goal says. */
export function buildPrompt(sc: Scenario): string {
  const goal = sc.goal.replace(/\.$/, "");
  return `Add a skill called "${sc.title}" that runs when ${sc.when}. Goal: ${goal.charAt(0).toLowerCase()}${goal.slice(1)}`;
}
