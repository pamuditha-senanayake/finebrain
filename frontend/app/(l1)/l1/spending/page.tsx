import type { Metadata } from "next";
import { SpendingView } from "@/features/l1/spending";

export const metadata: Metadata = { title: "Spending" };

export default function Page() {
  return <SpendingView />;
}
