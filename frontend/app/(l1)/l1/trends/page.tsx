import type { Metadata } from "next";
import { Trends } from "@/features/l1/trends";

export const metadata: Metadata = { title: "Trends" };

export default function Page() {
  return <Trends />;
}
