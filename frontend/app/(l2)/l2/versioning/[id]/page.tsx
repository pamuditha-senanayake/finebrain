import type { Metadata } from "next";
import { ChangeRequestDetail } from "@/features/l2/versioning";

export const metadata: Metadata = { title: "Change request" };

export default function Page() {
  return <ChangeRequestDetail />;
}
