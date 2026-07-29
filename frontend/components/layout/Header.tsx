"use client";

import { Search, Bell, Sun, Moon, PanelRightClose, PanelRight } from "lucide-react";
import { useUIStore } from "@/lib/store";
import styles from "./Header.module.css";

export default function Header() {
  const { theme, toggleTheme, inspectorOpen, toggleInspector, setCommandPaletteOpen } = useUIStore();

  return (
    <header className={styles.header}>
      <div className={styles.headerLeft}>
        <button
          className={styles.searchTrigger}
          onClick={() => setCommandPaletteOpen(true)}
        >
          <Search size={14} />
          <span>Search or type ⌘K...</span>
          <kbd className={styles.searchKbd}>⌘K</kbd>
        </button>
      </div>

      <div className={styles.headerRight}>
        <button
          className={styles.iconBtn}
          onClick={toggleTheme}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        <button className={styles.iconBtn} title="Notifications">
          <Bell size={16} />
        </button>

        <button
          className={styles.iconBtn}
          onClick={toggleInspector}
          title={inspectorOpen ? "Close inspector" : "Open inspector"}
        >
          {inspectorOpen ? <PanelRightClose size={16} /> : <PanelRight size={16} />}
        </button>

        <div className={styles.avatar} title="Madhu (Admin)">
          M
        </div>
      </div>
    </header>
  );
}
