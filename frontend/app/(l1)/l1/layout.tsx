import { AppShell } from "@/components/shell/app-shell";

export default function Layout({ children }: LayoutProps<"/l1">) {
  return <AppShell area="L1">{children}</AppShell>;
}
