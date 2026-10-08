import type { Metadata } from "next";
import { Security } from "@/features/l2/security";

export const metadata: Metadata = { title: "Security and access" };

export default function Page() {
  return <Security />;
}
