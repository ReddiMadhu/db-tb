"use client";

import React, { useEffect } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";
import Button from "@/components/ui/Button";
import styles from "./ConfirmationDialog.module.css";

export interface ConfirmationDialogProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "warning";
  isLoading?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export default function ConfirmationDialog({
  isOpen,
  title,
  description,
  confirmLabel = "Confirm Action",
  cancelLabel = "Cancel",
  variant = "danger",
  isLoading = false,
  onConfirm,
  onClose,
}: ConfirmationDialogProps) {
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
      >
        <div className={styles.header}>
          <div
            className={`${styles.iconWrapper} ${
              variant === "danger" ? styles.dangerIcon : styles.warningIcon
            }`}
          >
            {variant === "danger" ? <Trash2 size={22} /> : <AlertTriangle size={22} />}
          </div>
          <div className={styles.titleGroup}>
            <h2 id="confirm-dialog-title" className={styles.title}>
              {title}
            </h2>
            <p className={styles.description}>{description}</p>
          </div>
        </div>

        <div className={styles.actions}>
          <Button variant="ghost" onClick={onClose} disabled={isLoading}>
            {cancelLabel}
          </Button>
          <Button
            variant={variant === "danger" ? "danger" : "primary"}
            onClick={onConfirm}
            isLoading={isLoading}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
