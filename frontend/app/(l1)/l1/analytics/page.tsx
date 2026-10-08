import type { Metadata } from "next";
import { Analytics } from "@/features/l1/analytics";

export const metadata: Metadata = { title: "Progress and analytics" };

export default function Page() {
  return <Analytics />;
}
