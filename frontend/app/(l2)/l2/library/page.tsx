import type { Metadata } from "next";
import { LibraryView } from "@/features/l2/library";

export const metadata: Metadata = { title: "Library" };

export default function Page() {
  return <LibraryView />;
}
