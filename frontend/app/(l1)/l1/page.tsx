import type { Metadata } from "next";
import { Overview } from "@/features/l1/overview";

export const metadata: Metadata = { title: "Brain overview" };

export default function Page() {
  return <Overview />;
}
