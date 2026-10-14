import type { Metadata } from "next";
import { ApprovalsInbox } from "@/features/l1/approvals";

export const metadata: Metadata = { title: "All approvals" };

export default function Page() {
  return <ApprovalsInbox />;
}
