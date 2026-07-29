"use client";

import React, { useEffect } from "react";
import { CheckCircle2, ArrowRight } from "lucide-react";
import Button from "@/components/ui/Button";
import styles from "./SuccessDialog.module.css";

export interface SuccessDialogProps {
  isOpen: boolean;
  title: string;
  description: string;
  details?: Array<{ label: string; value: string }>;
  primaryActionLabel?: string;
  secondaryActionLabel?: string;
  onPrimaryAction?: () => void;
  onSecondaryAction?: () => void;
  onClose: () => void;
}

export default function SuccessDialog({
  isOpen,
  title,
  description,
  details,
  primaryActionLabel = "Continue",
  secondaryActionLabel = "Close",
  onPrimaryAction,
  onSecondaryAction,
  onClose,
}: SuccessDialogProps) {
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
        aria-labelledby="success-dialog-title"
      >
        <div className={styles.iconCircle}>
          <CheckCircle2 size={32} />
        </div>

        <h2 id="success-dialog-title" className={styles.title}>
          {title}
        </h2>
        <p className={styles.description}>{description}</p>

        {details && details.length > 0 && (
          <div className={styles.detailBox}>
            {details.map((d, i) => (
              <div key={i} className={styles.detailRow}>
                <span className={styles.detailLabel}>{d.label}</span>
                <span className={`${styles.detailValue} mono`}>{d.value}</span>
              </div>
            ))}
          </div>
        )}

        <div className={styles.actions}>
          {secondaryActionLabel && (
            <Button
              variant="secondary"
              onClick={() => {
                if (onSecondaryAction) onSecondaryAction();
                onClose();
              }}
            >
              {secondaryActionLabel}
            </Button>
          )}
          {primaryActionLabel && onPrimaryAction && (
            <Button
              variant="primary"
              icon={<ArrowRight size={16} />}
              onClick={() => {
                onPrimaryAction();
                onClose();
              }}
            >
              {primaryActionLabel}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
