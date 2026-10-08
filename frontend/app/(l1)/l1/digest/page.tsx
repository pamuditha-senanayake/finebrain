import type { Metadata } from "next";
import { Digest } from "@/features/l1/digest";

export const metadata: Metadata = { title: "Morning digest" };

export default function Page() {
  return <Digest />;
}
