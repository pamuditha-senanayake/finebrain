import type { Metadata } from "next";
import { Templates } from "@/features/l2/templates";

export const metadata: Metadata = { title: "Templates" };

export default function Page() {
  return <Templates />;
}
