import type { Metadata } from "next";
import { TasksView } from "@/features/l1/tasks";

export const metadata: Metadata = { title: "Tasks" };

export default function Page() {
  return <TasksView />;
}
