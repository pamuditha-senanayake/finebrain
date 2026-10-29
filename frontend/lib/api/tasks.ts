"use client";

// tasks.ts: A3's tasks. Read the list, add one by hand, change one (owner, day, done). Backend tasks.py.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import * as C from "@/contracts";
import { reportError } from "@/lib/errors";
import { useUi } from "@/lib/store";
import { apiPost } from "./client";
import { useResource } from "./hooks";

export const useTasks = () => useResource("tasks", z.array(C.Task));

function useTaskWrite<T>(op: string, call: (input: T) => Promise<C.Task>) {
  const qc = useQueryClient();
  const tenantId = useUi((s) => s.tenantId);
  return useMutation({
    mutationFn: call,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["t", tenantId, "tasks"] }),
    onError: (e) => reportError(e, { op }),
  });
}

export const useAddTask = () => useTaskWrite("tasks.add", (task: { title: string; owner: string; due?: string }) => apiPost("tasks", task, C.Task));
export const useChangeTask = () => useTaskWrite("tasks.change", ({ id, ...change }: { id: string } & Partial<Pick<C.Task, "title" | "owner" | "due" | "status">>) => apiPost(`tasks/${id}`, change, C.Task));
