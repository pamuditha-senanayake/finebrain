import type { Metadata } from "next";
import { PolicyRegistry } from "@/features/l2/policies";

export const metadata: Metadata = { title: "Policy registry" };

export default function Page() {
  return <PolicyRegistry />;
}
