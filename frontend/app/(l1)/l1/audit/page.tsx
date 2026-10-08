import type { Metadata } from "next";
import { AuditTrail } from "@/features/l1/audit";

export const metadata: Metadata = { title: "Audit trail" };

export default function Page() {
  return <AuditTrail />;
}
