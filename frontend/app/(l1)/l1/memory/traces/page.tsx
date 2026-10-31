import type { Metadata } from "next";
import { Traces } from "@/features/l1/memory/traces";

export const metadata: Metadata = { title: "Traces" };

export default function Page() {
  return <Traces />;
}
