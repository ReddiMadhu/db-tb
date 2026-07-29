"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  LayoutDashboard,
  FolderKanban,
  ArrowRightLeft,
  ShieldCheck,
  Rocket,
  BookOpen,
  BarChart3,
  Database,
  FileBarChart,
  Activity,
  PlugZap,
  Settings,
  PanelLeftClose,
  PanelLeft,
  Zap,
} from "lucide-react";
import { useUIStore } from "@/lib/store";
import styles from "./Sidebar.module.css";

interface NavItemProps {
  href: string;
  icon: React.ReactNode;
  label: string;
  collapsed: boolean;
}

function NavItem({ href, icon, label, collapsed }: NavItemProps) {
  const pathname = usePathname();
  const isActive = pathname === href || (href !== "/" && pathname.startsWith(href));

  return (
    <Link
      href={href}
      className={`${styles.navItem} ${isActive ? styles.active : ""}`}
      title={collapsed ? label : undefined}
    >
      <span className={styles.navItemIcon}>{icon}</span>
      <span className={styles.navItemLabel}>{label}</span>
    </Link>
  );
}

const NAV_SECTIONS = [
  {
    label: "Work",
    items: [
      { href: "/", icon: <LayoutDashboard size={18} />, label: "Dashboard" },
      { href: "/projects", icon: <FolderKanban size={18} />, label: "Projects" },
      { href: "/migrations", icon: <ArrowRightLeft size={18} />, label: "Migrations" },
      { href: "/validation", icon: <ShieldCheck size={18} />, label: "Validation" },
      { href: "/deployments", icon: <Rocket size={18} />, label: "Deployments" },
    ],
  },
  {
    label: "Assets",
    items: [
      { href: "/workbooks", icon: <BookOpen size={18} />, label: "Workbooks" },
      { href: "/dashboards", icon: <BarChart3 size={18} />, label: "Dashboards" },
      { href: "/datasets", icon: <Database size={18} />, label: "Datasets" },
    ],
  },
  {
    label: "Insights",
    items: [
      { href: "/reports", icon: <FileBarChart size={18} />, label: "Reports" },
      { href: "/activity", icon: <Activity size={18} />, label: "Activity" },
    ],
  },
  {
    label: "Platform",
    items: [
      { href: "/connections", icon: <PlugZap size={18} />, label: "Connections" },
      { href: "/settings", icon: <Settings size={18} />, label: "Settings" },
    ],
  },
];

export default function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useUIStore();

  return (
    <aside
      className={`${styles.sidebar} ${sidebarCollapsed ? styles.collapsed : ""}`}
    >
      <div className={styles.sidebarHeader}>
        <div className={styles.logo}>
          <div className={styles.logoIcon}>
            <Zap size={14} color="white" />
          </div>
          {!sidebarCollapsed && <span>LakeShift</span>}
        </div>
        <button
          className={styles.collapseBtn}
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? <PanelLeft size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <nav className={styles.navContent}>
        {NAV_SECTIONS.map((section) => (
          <div key={section.label} className={styles.navSection}>
            <div className={styles.navSectionLabel}>{section.label}</div>
            {section.items.map((item) => (
              <NavItem
                key={item.href}
                href={item.href}
                icon={item.icon}
                label={item.label}
                collapsed={sidebarCollapsed}
              />
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
