import { AppShell } from "@/components/shell/app-shell";

export default function Layout({ children }: LayoutProps<"/l2">) {
  return <AppShell area="L2">{children}</AppShell>;
}
