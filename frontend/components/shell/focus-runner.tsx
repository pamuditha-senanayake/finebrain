"use client";

import { useEffect } from "react";
import { useFocusTarget } from "@/lib/focus";
import { showMe } from "@/lib/focus-fx";

/** Mounted once. Whenever the address has ?focus=kind:id, finds that element on the page and shows it (lib/focus-fx.ts). */
export function FocusRunner() {
  const target = useFocusTarget();
  const key = target?.key;
  useEffect(() => (target ? showMe(target) : undefined), [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}
