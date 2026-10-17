import { redirect } from "next/navigation";

/** Evidence requests now live inside To review. */
export default function Page() {
  redirect("/l1/digest?tab=evidence");
}
