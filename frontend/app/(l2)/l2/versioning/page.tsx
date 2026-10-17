import type { Metadata } from "next";
import { Versioning } from "@/features/l2/versioning";

export const metadata: Metadata = { title: "Versions" };

export default function Page() {
  return <Versioning />;
}
