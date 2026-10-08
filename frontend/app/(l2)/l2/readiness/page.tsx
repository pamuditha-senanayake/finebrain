import type { Metadata } from "next";
import { Readiness } from "@/features/l2/readiness";

export const metadata: Metadata = { title: "Readiness scheduler" };

export default function Page() {
  return <Readiness />;
}
