import type { Metadata } from "next";
import { EvidenceRequests } from "@/features/l1/evidence";

export const metadata: Metadata = { title: "Evidence requests" };

export default function Page() {
  return <EvidenceRequests />;
}
