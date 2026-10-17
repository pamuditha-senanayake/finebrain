import { redirect } from "next/navigation";

/** Approvals now live inside To review. */
export default function Page() {
  redirect("/l1/digest?tab=approvals");
}
