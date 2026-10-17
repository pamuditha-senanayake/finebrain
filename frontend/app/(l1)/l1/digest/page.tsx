import type { Metadata } from "next";
import { Digest } from "@/features/l1/digest";

export const metadata: Metadata = { title: "To review" };

export default function Page() {
  return <Digest />;
}
