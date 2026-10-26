import { redirect } from "next/navigation";

// Sensors now live inside Connections: a connection's feed is its sensor.
export default function Page() {
  redirect("/l2/connections");
}
