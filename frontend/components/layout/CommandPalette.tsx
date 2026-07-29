"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, FolderOpen, GitBranch, CheckCircle2, Rocket, FileSpreadsheet, Settings, Plus } from "lucide-react";
import { useUIStore } from "@/lib/store";
import styles from "./CommandPalette.module.css";

export default function CommandPalette() {
  const { commandPaletteOpen, setCommandPaletteOpen } = useUIStore();
  const [query, setQuery] = useState("");
  const router = RouterHook();

  function RouterHook() {
    return useRouter();
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCommandPaletteOpen(!commandPaletteOpen);
      }
      if (e.key === "Escape" && commandPaletteOpen) {
        setCommandPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [commandPaletteOpen, setCommandPaletteOpen]);

  if (!commandPaletteOpen) return null;

  const COMMANDS = [
    { label: "Upload Workbook (.twbx)", icon: <Plus size={16} />, action: () => { router.push("/projects"); setCommandPaletteOpen(false); } },
    { label: "Go to Projects", icon: <FolderOpen size={16} />, action: () => { router.push("/projects"); setCommandPaletteOpen(false); } },
    { label: "Go to Validation Center", icon: <CheckCircle2 size={16} />, action: () => { router.push("/validation"); setCommandPaletteOpen(false); } },
    { label: "Go to Deployments", icon: <Rocket size={16} />, action: () => { router.push("/deployments"); setCommandPaletteOpen(false); } },
    { label: "Go to Workbooks", icon: <FileSpreadsheet size={16} />, action: () => { router.push("/workbooks"); setCommandPaletteOpen(false); } },
    { label: "Go to Settings", icon: <Settings size={16} />, action: () => { router.push("/settings"); setCommandPaletteOpen(false); } },
  ];

  const filtered = COMMANDS.filter((c) =>
    c.label.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className={styles.overlay} onClick={() => setCommandPaletteOpen(false)}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.inputWrapper}>
          <Search size={18} color="var(--text-tertiary)" />
          <input
            className={styles.input}
            placeholder="Type a command or search..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
        </div>

        <div className={styles.list}>
          <div className={styles.group}>
            <div className={styles.groupTitle}>Actions & Navigation</div>
            {filtered.map((cmd, idx) => (
              <div
                key={idx}
                className={styles.item}
                onClick={cmd.action}
              >
                <span className={styles.itemIcon}>{cmd.icon}</span>
                <span>{cmd.label}</span>
                <span className={styles.kbdHint}>↵ Jump</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
