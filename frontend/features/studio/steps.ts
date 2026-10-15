// The parts pane walks a workflow as a story: the problem and its cases first, then the parts in the same
// left to right order as the diagram's columns.
import type { MemberKind, StudioKind } from "@/contracts";

export type StepKey = "story" | "start" | "team" | "work" | "rules" | "results";

export type Step = { key: StepKey; label: string; hint: string; kinds: MemberKind[] };

export const STEPS: Step[] = [
  { key: "story", label: "Story", hint: "The problem, and the cases it must handle", kinds: [] },
  { key: "start", label: "Start", hint: "What wakes it", kinds: ["sensor", "scheduler"] },
  { key: "team", label: "Team", hint: "Who does the work", kinds: ["agent"] },
  { key: "work", label: "Work", hint: "What they do", kinds: ["skill"] },
  { key: "rules", label: "Rules & tools", hint: "What limits and powers them", kinds: ["policy", "tool"] },
  { key: "results", label: "Results", hint: "What it reports and learns", kinds: ["template", "loop"] },
];

export function stepOf(kind: StudioKind): StepKey | null {
  if (kind === "workflow") return "story";
  return STEPS.find((s) => (s.kinds as StudioKind[]).includes(kind))?.key ?? null;
}
