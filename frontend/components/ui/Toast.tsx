"use client";

import { CheckCircle2, CircleAlert, TriangleAlert, Info, X } from "lucide-react";
import styles from "./Toast.module.css";

export interface ToastMessage {
  id: string;
  type: "success" | "error" | "warning" | "info";
  title?: string;
  message: string;
}

interface ToastProps {
  toast: ToastMessage;
  onDismiss: (id: string) => void;
}

export default function Toast({ toast, onDismiss }: ToastProps) {
  const getIcon = () => {
    switch (toast.type) {
      case "success":
        return <CheckCircle2 size={18} color="var(--accent-green)" />;
      case "error":
        return <CircleAlert size={18} color="var(--accent-red)" />;
      case "warning":
        return <TriangleAlert size={18} color="var(--accent-amber)" />;
      case "info":
      default:
        return <Info size={18} color="var(--accent-info)" />;
    }
  };

  return (
    <div className={`${styles.toast} ${styles[toast.type]}`}>
      <div className={styles.iconContainer}>{getIcon()}</div>
      <div className={styles.content}>
        {toast.title && <div className={styles.title}>{toast.title}</div>}
        <div className={styles.message}>{toast.message}</div>
      </div>
      <button
        className={styles.dismissBtn}
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
      >
        <X size={14} />
      </button>
    </div>
  );
}
