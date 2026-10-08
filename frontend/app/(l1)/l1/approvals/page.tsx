import type { Metadata } from "next";
import { ApprovalsInbox } from "@/features/l1/approvals";

export const metadata: Metadata = { title: "Approvals" };

export default function Page() {
  return <ApprovalsInbox />;
}
