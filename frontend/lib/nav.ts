import {
  Activity,
  TrendingUp,
  AlarmClock,
  AudioLines,
  BarChart3,
  Beaker,
  BookOpen,
  Boxes,
  Bot,
  CalendarClock,
  ClipboardList,
  FlaskConical,
  GraduationCap,
  Inbox,
  LayoutDashboard,
  ListTodo,
  Lock,
  Library,
  MessagesSquare,
  Network,
  Plug,
  Repeat,
  Route,
  ScrollText,
  Settings2,
  ShieldCheck,
  Siren,
  Table2,
  Vault,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import type { Area } from "@/lib/auth";
import type { MessageKey } from "@/lib/i18n";

export type NavItem = {
  href: string;
  label: MessageKey;
  icon: LucideIcon;
  exact?: boolean;
  /** Items sharing a group render together; a divider separates groups. */
  group?: number;
  /** Other routes that live inside this page (e.g. a detail page), so the item stays highlighted there. */
  also?: string[];
};
export type NavArea = { area: Area; label: MessageKey; home: string; items: NavItem[] };

export const NAV: NavArea[] = [
  {
    area: "L1",
    label: "tier.L1",
    home: "/l1",
    items: [
      { href: "/l1", label: "nav.overview", icon: LayoutDashboard, exact: true, group: 0 },
      { href: "/l1/ask", label: "nav.ask", icon: AudioLines, group: 0 },
      // To review holds approvals and evidence requests as tabs.
      { href: "/l1/digest", label: "nav.digest", icon: Inbox, group: 0, also: ["/l1/approvals", "/l1/evidence"] },
      { href: "/l1/tasks", label: "nav.tasks", icon: ListTodo, group: 0 },
      { href: "/l1/claude", label: "nav.claude", icon: Bot, group: 0 },
      // Workflow Studio is the main feature, so it gets a section of its own.
      { href: "/studio", label: "nav.studio", icon: Workflow, group: 1 },
      { href: "/l1/entity", label: "nav.entity", icon: CalendarClock, group: 2 },
      { href: "/l1/analytics", label: "nav.analytics", icon: BarChart3, group: 2 },
      { href: "/l1/trends", label: "nav.trends", icon: TrendingUp, group: 2 },
      { href: "/l1/audit", label: "nav.audit", icon: ScrollText, group: 2 },
      { href: "/l1/setup", label: "nav.setup", icon: Settings2, group: 3 },
    ],
  },
  {
    area: "L2",
    label: "tier.L2",
    home: "/l2/vault",
    items: [
      // Where people act: resolve conflicts and keep access safe.
      { href: "/l2/vault", label: "nav.vault", icon: Vault, group: 0 },
      { href: "/l2/security", label: "nav.security", icon: ShieldCheck, group: 0 },
      // Find things. Versions sit in a tab inside the graph.
      { href: "/l2/graph", label: "nav.graph", icon: Network, group: 1, also: ["/l2/versioning"] },
      { href: "/l2/library", label: "nav.library", icon: Library, group: 1 },
      // Overviews: read only.
      { href: "/l2/policies", label: "nav.policies", icon: BookOpen, group: 2 },
      { href: "/l2/skills", label: "nav.skills", icon: GraduationCap, group: 2 },
      { href: "/l2/resolver", label: "nav.resolver", icon: Route, group: 2 },
      { href: "/l2/templates", label: "nav.templates", icon: ClipboardList, group: 2 },
      { href: "/l2/connections", label: "nav.connections", icon: Plug, group: 2, also: ["/l2/sensors"] },
      { href: "/l2/loops", label: "nav.loops", icon: Repeat, group: 2 },
      { href: "/l2/readiness", label: "nav.readiness", icon: AlarmClock, group: 2 },
      { href: "/studio", label: "nav.studioL2", icon: Workflow, group: 3 },
    ],
  },
  {
    area: "L3",
    label: "tier.L3",
    home: "/l3/conversations",
    items: [
      // The human in the loop acts here: take over a live conversation or an escalation.
      { href: "/l3/conversations", label: "nav.conversations", icon: MessagesSquare, group: 0 },
      { href: "/l3/escalations", label: "nav.escalations", icon: Siren, group: 0 },
      // Overviews.
      { href: "/l3", label: "nav.fleet", icon: Boxes, exact: true, group: 1, also: ["/l3/agents"] },
      { href: "/l3/runs", label: "nav.runs", icon: Activity, group: 1 },
      { href: "/l3/templates", label: "nav.templateBoard", icon: Table2, group: 2 },
    ],
  },
];

export const RESEARCH_NAV: NavArea = {
  area: "research",
  label: "tier.research",
  home: "/research",
  items: [
    { href: "/research", label: "nav.research", icon: FlaskConical, exact: true, also: ["/research/policies", "/research/skills", "/research/security", "/research/integration"] },
    { href: "/research/lab", label: "nav.lab", icon: Beaker, also: ["/research/lab/new"] },
    { href: "/research/prereg", label: "nav.prereg", icon: Lock },
  ],
};

export const AREA_ICON: Record<Area, LucideIcon> = { L1: LayoutDashboard, L2: ShieldCheck, L3: Activity, research: FlaskConical };
