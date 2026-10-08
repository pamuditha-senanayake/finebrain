import type { Metadata } from "next";
import { TemplateBoard } from "@/features/l3/template-board";

export const metadata: Metadata = { title: "Template board" };

export default function Page() {
  return <TemplateBoard />;
}
