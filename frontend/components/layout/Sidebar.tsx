"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import {
  LayoutDashboard,
  ArrowRightLeft,
  Rocket,
  PlugZap,
  Settings,
  PanelLeftClose,
  PanelLeft,
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
      { href: "/migrations", icon: <ArrowRightLeft size={18} />, label: "Migrations" },
    ],
  },
  {
    label: "Operations",
    items: [
      { href: "/deployments", icon: <Rocket size={18} />, label: "Deployments" },
      { href: "/connections", icon: <PlugZap size={18} />, label: "Connections" },
    ],
  },
  {
    label: "System",
    items: [
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
            <ArrowRightLeft size={14} color="white" />
          </div>
          {!sidebarCollapsed && (
            <div className={styles.logoText}>
              <span className={styles.logoLine1}>Tableau to</span>
              <span className={styles.logoLine2}>Databricks</span>
            </div>
          )}
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
