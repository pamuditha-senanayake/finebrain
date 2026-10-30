import type { Metadata } from "next";
import { LivingMemory } from "@/features/l1/memory/memory";

export const metadata: Metadata = { title: "Living memory" };

export default function Page() {
  return <LivingMemory />;
}
