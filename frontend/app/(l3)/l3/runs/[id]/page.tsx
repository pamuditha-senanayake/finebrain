import type { Metadata } from "next";
import { RunTrace } from "@/features/l3/run-trace";

export const metadata: Metadata = { title: "Run trace" };

export default function Page() {
  return <RunTrace />;
}
