import type { Metadata } from "next";
import { PolicyDetail } from "@/features/l2/policies";

export const metadata: Metadata = { title: "Policy" };

export default function Page() {
  return <PolicyDetail />;
}
