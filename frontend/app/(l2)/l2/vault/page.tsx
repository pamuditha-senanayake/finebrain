import type { Metadata } from "next";
import { Vault } from "@/features/l2/vault";

export const metadata: Metadata = { title: "Ground truth vault" };

export default function Page() {
  return <Vault />;
}
