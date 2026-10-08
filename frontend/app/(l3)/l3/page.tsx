import type { Metadata } from "next";
import { Fleet } from "@/features/l3/fleet";

export const metadata: Metadata = { title: "Fleet" };

export default function Page() {
  return <Fleet />;
}
