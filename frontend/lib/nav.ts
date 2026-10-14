import {
  Activity,
  AlarmClock,
  BarChart3,
  BookOpen,
  Boxes,
  CalendarClock,
  ClipboardList,
  FileCheck2,
  FlaskConical,
  GitBranch,
  GraduationCap,
  Inbox,
  LayoutDashboard,
  Library,
  MessagesSquare,
  Network,
  Radar,
  Repeat,
  Route,
  ScrollText,
  ShieldCheck,
  Siren,
  Sunrise,
  Table2,
  Vault,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import type { Area } from "@/lib/auth";
import type { MessageKey } from "@/lib/i18n";

export type NavItem = { href: string; label: MessageKey; icon: LucideIcon; exact?: boolean; /** Items sharing a group render together; a divider separates groups. */ group?: number };
export type NavArea = { area: Area; label: MessageKey; home: string; items: NavItem[] };

export const NAV: NavArea[] = [
  {
    area: "L1",
    label: "tier.L1",
    home: "/l1",
    items: [
      { href: "/l1", label: "nav.overview", icon: LayoutDashboard, exact: true, group: 0 },
      { href: "/l1/digest", label: "nav.digest", icon: Sunrise, group: 0 },
      { href: "/l1/approvals", label: "nav.approvals", icon: Inbox, group: 1 },
      { href: "/studio", label: "nav.studio", icon: Workflow, group: 1 },
      { href: "/l1/entity", label: "nav.entity", icon: CalendarClock, group: 1 },
      { href: "/l1/evidence", label: "nav.evidence", icon: FileCheck2, group: 1 },
      { href: "/l1/analytics", label: "nav.analytics", icon: BarChart3, group: 2 },
      { href: "/l1/audit", label: "nav.audit", icon: ScrollText, group: 3 },
    ],
  },
  {
    area: "L2",
    label: "tier.L2",
    home: "/l2/graph",
    items: [
      { href: "/l2/graph", label: "nav.graph", icon: Network, group: 0 },
      { href: "/l2/versioning", label: "nav.versioning", icon: GitBranch, group: 0 },
      { href: "/l2/library", label: "nav.library", icon: Library, group: 1 },
      { href: "/l2/vault", label: "nav.vault", icon: Vault, group: 1 },
      { href: "/l2/policies", label: "nav.policies", icon: BookOpen, group: 2 },
      { href: "/l2/skills", label: "nav.skills", icon: GraduationCap, group: 2 },
      { href: "/l2/resolver", label: "nav.resolver", icon: Route, group: 2 },
      { href: "/l2/templates", label: "nav.templates", icon: ClipboardList, group: 2 },
      { href: "/l2/sensors", label: "nav.sensors", icon: Radar, group: 2 },
      { href: "/l2/loops", label: "nav.loops", icon: Repeat, group: 3 },
      { href: "/l2/readiness", label: "nav.readiness", icon: AlarmClock, group: 3 },
      { href: "/l2/security", label: "nav.security", icon: ShieldCheck, group: 3 },
      { href: "/studio", label: "nav.studioL2", icon: Workflow, group: 4 },
    ],
  },
  {
    area: "L3",
    label: "tier.L3",
    home: "/l3",
    items: [
      { href: "/l3", label: "nav.fleet", icon: Boxes, exact: true, group: 0 },
      { href: "/l3/runs", label: "nav.runs", icon: Activity, group: 0 },
      { href: "/l3/conversations", label: "nav.conversations", icon: MessagesSquare, group: 1 },
      { href: "/l3/escalations", label: "nav.escalations", icon: Siren, group: 1 },
      { href: "/l3/templates", label: "nav.templateBoard", icon: Table2, group: 2 },
    ],
  },
];

export const RESEARCH_NAV: NavArea = { area: "research", label: "tier.research", home: "/research", items: [{ href: "/research", label: "nav.research", icon: FlaskConical, exact: true }] };

export const AREA_ICON: Record<Area, LucideIcon> = { L1: LayoutDashboard, L2: ShieldCheck, L3: Activity, research: FlaskConical };
