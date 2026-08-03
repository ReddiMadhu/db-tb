import { Check, Loader2, AlertTriangle, XCircle, SkipForward, Clock } from "lucide-react";
import type { StageStatus } from "@/lib/types";
import styles from "./StatusBadge.module.css";

interface StatusBadgeProps {
  status: StageStatus | string;
  size?: "sm" | "md";
}

const STATUS_CONFIG: Record<string, { icon: React.ReactNode; label: string; className: string }> = {
  WAITING: { icon: <Clock size={12} />, label: "Waiting", className: "waiting" },
  RUNNING: { icon: <Loader2 size={12} className="spin" />, label: "Running", className: "running" },
  COMPLETED: { icon: <Check size={12} />, label: "Completed", className: "completed" },
  WARNING: { icon: <AlertTriangle size={12} />, label: "Warning", className: "warning" },
  FAILED: { icon: <XCircle size={12} />, label: "Failed", className: "failed" },
  SKIPPED: { icon: <SkipForward size={12} />, label: "Skipped", className: "skipped" },
  // Legacy statuses for backward compatibility
  DEPLOYED: { icon: <Check size={12} />, label: "Deployed", className: "completed" },
  PARSED: { icon: <Check size={12} />, label: "Parsed", className: "completed" },
  EXECUTING: { icon: <Loader2 size={12} className="spin" />, label: "Executing", className: "running" },
  NEEDS_MAPPING: { icon: <AlertTriangle size={12} />, label: "Needs Mapping", className: "warning" },
  NEEDS_REVIEW: { icon: <AlertTriangle size={12} />, label: "Needs Review", className: "warning" },
};

export default function StatusBadge({ status, size = "sm" }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.WAITING;

  return (
    <span className={`${styles.badge} ${styles[config.className]} ${size === "md" ? styles.md : ""}`}>
      {config.icon}
      <span>{config.label}</span>
    </span>
  );
}
