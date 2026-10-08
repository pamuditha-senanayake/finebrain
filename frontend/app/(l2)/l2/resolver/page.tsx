import type { Metadata } from "next";
import { Resolver } from "@/features/l2/resolver";

export const metadata: Metadata = { title: "Resolver" };

export default function Page() {
  return <Resolver />;
}
