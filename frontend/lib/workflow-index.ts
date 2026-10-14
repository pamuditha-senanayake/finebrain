"use client";

import { useMemo } from "react";
import { useStudioWorkflows } from "@/lib/api/hooks";

/**
 * Which workflows each part belongs to. A workflow's members are ids like `care.skill.sk-1`
 * (workflow key, kind, part id), so any part can be traced back to its workflows.
 */
export function useWorkflowIndex() {
  const workflows = useStudioWorkflows();
  return useMemo(() => {
    const by = new Map<string, string[]>();
    for (const w of workflows.data ?? []) {
      for (const m of w.members) {
        const a = m.indexOf(".");
        const b = m.indexOf(".", a + 1);
        if (a < 0 || b < 0) continue;
        const k = `${m.slice(a + 1, b)}:${m.slice(b + 1)}`;
        const cur = by.get(k) ?? [];
        if (!cur.includes(w.name)) cur.push(w.name);
        by.set(k, cur);
      }
    }
    return { of: (kind: string, id: string): string[] => by.get(`${kind}:${id}`) ?? [] };
  }, [workflows.data]);
}
