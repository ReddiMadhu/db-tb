"use client";

import { AlertCircle, AlertTriangle, Info, Sparkles, FileSearch } from "lucide-react";
import Button from "@/components/ui/Button";
import styles from "./ValidationCard.module.css";

interface ValidationCardProps {
  type: "error" | "warning" | "info";
  message: string;
  tier?: string;
  onAiFix?: () => void;
  onInspect?: () => void;
}

export default function ValidationCard({
  type,
  message,
  tier = "Schema Validation",
  onAiFix,
  onInspect,
}: ValidationCardProps) {
  let Icon = AlertCircle;
  let typeClass = styles.error;
  if (type === "warning") {
    Icon = AlertTriangle;
    typeClass = styles.warning;
  } else if (type === "info") {
    Icon = Info;
    typeClass = styles.info;
  }

  return (
    <div className={styles.card}>
      <div className={`${styles.header} ${typeClass}`}>
        <Icon size={16} />
        <span>
          {type.toUpperCase()} • {tier}
        </span>
      </div>

      <div className={styles.message}>{message}</div>

      <div className={styles.actions}>
        <Button variant="primary" size="sm" icon={<Sparkles size={12} />} onClick={onAiFix}>
          AI Quick Fix
        </Button>
        <Button variant="secondary" size="sm" icon={<FileSearch size={12} />} onClick={onInspect}>
          Inspect Details
        </Button>
      </div>
    </div>
  );
}
