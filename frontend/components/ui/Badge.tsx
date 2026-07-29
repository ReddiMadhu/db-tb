import type { JobStatus } from "@/lib/types";
import styles from "./Badge.module.css";

interface BadgeProps {
  status: JobStatus | string;
  label?: string;
}

export default function Badge({ status, label }: BadgeProps) {
  const normalized = status.toLowerCase() as keyof typeof styles;
  const badgeClass = styles[normalized] || styles.uploaded;

  return (
    <span className={`${styles.badge} ${badgeClass}`}>
      ● {label || status}
    </span>
  );
}
