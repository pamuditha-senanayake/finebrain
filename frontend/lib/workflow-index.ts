"use client";

import { useMemo } from "react";
import { useStudioWorkflows } from "@/lib/api/hooks";

export type WorkflowLink = { wfId: string; wfName: string; memberId: string; topic: string };

/**
 * Which workflows each part belongs to. A workflow's members are ids like `care.skill.sk-1`
 * (workflow key, kind, part id), so any part can be traced back to its workflows.
 */
export function useWorkflowIndex() {
  const workflows = useStudioWorkflows();
  return useMemo(() => {
    const by = new Map<string, WorkflowLink[]>();
    for (const w of workflows.data ?? []) {
      for (const m of w.members) {
        const a = m.indexOf(".");
        const b = m.indexOf(".", a + 1);
        if (a < 0 || b < 0) continue;
        const k = `${m.slice(a + 1, b)}:${m.slice(b + 1)}`;
        const cur = by.get(k) ?? [];
        if (!cur.some((x) => x.wfId === w.id)) cur.push({ wfId: w.id, wfName: w.name, memberId: m, topic: w.topics[0] ?? "general" });
        by.set(k, cur);
      }
    }
    return {
      of: (kind: string, id: string): string[] => (by.get(`${kind}:${id}`) ?? []).map((x) => x.wfName),
      links: (kind: string, id: string): WorkflowLink[] => by.get(`${kind}:${id}`) ?? [],
      /** A part's category: the lead topic of the first workflow it belongs to. */
      category: (kind: string, id: string): string => by.get(`${kind}:${id}`)?.[0]?.topic ?? "general",
    };
  }, [workflows.data]);
}

/** Link that opens a part in Workflow Studio, on its workflow with the part selected. */
export const studioHref = (l: WorkflowLink) => `/studio?wf=${l.wfId}&focus=${encodeURIComponent(l.memberId)}&view=chat`;
