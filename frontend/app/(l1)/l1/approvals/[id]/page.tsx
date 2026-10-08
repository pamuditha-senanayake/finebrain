import type { Metadata } from "next";
import { ApprovalDetail } from "@/features/l1/approvals";

export const metadata: Metadata = { title: "Approval" };

export default function Page() {
  return <ApprovalDetail />;
}
