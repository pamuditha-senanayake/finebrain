import { AppShell } from "@/components/shell/app-shell";

export default function Layout({ children }: LayoutProps<"/l3">) {
  return <AppShell area="L3">{children}</AppShell>;
}
