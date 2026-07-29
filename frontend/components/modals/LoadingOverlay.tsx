"use client";

import React, { useEffect } from "react";
import Button from "@/components/ui/Button";
import styles from "./LoadingOverlay.module.css";

export interface LoadingOverlayProps {
  isOpen: boolean;
  title: string;
  stageText?: string;
  taskDescription?: string;
  progressPercent?: number;
  onCancel?: () => void;
}

export default function LoadingOverlay({
  isOpen,
  title,
  stageText = "Processing...",
  taskDescription = "Pipeline execution in progress...",
  progressPercent = 0,
  onCancel,
}: LoadingOverlayProps) {
  useEffect(() => {
    if (!isOpen) return;

    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const clampProgress = Math.min(100, Math.max(0, Math.round(progressPercent)));

  return (
    <div className={styles.backdrop}>
      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="loading-overlay-title"
      >
        <div className={styles.spinnerContainer}>
          <div className={styles.spinnerRing} />
          <span className={`${styles.percentText} mono`}>{clampProgress}%</span>
        </div>

        <div className={styles.stageBadge}>{stageText}</div>
        <h2 id="loading-overlay-title" className={styles.title}>
          {title}
        </h2>
        <p className={styles.taskDesc}>{taskDescription}</p>

        <div className={styles.progressTrack}>
          <div className={styles.progressBar} style={{ width: `${clampProgress}%` }} />
        </div>

        {onCancel && (
          <div className={styles.cancelRow}>
            <Button variant="ghost" size="sm" onClick={onCancel}>
              Cancel Operation
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
