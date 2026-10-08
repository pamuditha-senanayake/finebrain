import type { Metadata } from "next";
import { Home } from "@/features/home";

export const metadata: Metadata = { title: "Company Brain" };

export default function Page() {
  return <Home />;
}
