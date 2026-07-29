"use client";

import React, { useState, useEffect } from "react";
import {
  AlertCircle,
  Copy,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  Play,
  Download,
  FileCode,
  Bug,
  X,
  Check,
} from "lucide-react";
import Button from "@/components/ui/Button";
import styles from "./ErrorDialog.module.css";

export interface ErrorDialogProps {
  isOpen: boolean;
  title?: string;
  message: string;
  technicalDetails?: string;
  requestId?: string;
  onRetry?: () => void;
  onResume?: () => void;
  onDownloadLogs?: () => void;
  onViewSql?: () => void;
  onReportBug?: () => void;
  onClose: () => void;
}

// Redact tokens/passwords from error traces
function sanitizeErrorTrace(text?: string): string {
  if (!text) return "";
  return text
    .replace(/(dapi-[a-zA-Z0-9_-]{10,})/g, "dapi-••••••••••••")
    .replace(/("token"|"password"|"api_key"|"key")\s*:\s*"[^"]+"/gi, '$1: "••••••••"');
}

export default function ErrorDialog({
  isOpen,
  title = "Operation Failed",
  message,
  technicalDetails,
  requestId: customRequestId,
  onRetry,
  onResume,
  onDownloadLogs,
  onViewSql,
  onReportBug,
  onClose,
}: ErrorDialogProps) {
  const [showDetails, setShowDetails] = useState(false);
  const [copied, setCopied] = useState(false);
  const [generatedId] = useState(() => customRequestId || `req-${Math.random().toString(36).slice(2, 8).toUpperCase()}`);

  const activeRequestId = customRequestId || generatedId;

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleCopyRequestId = () => {
    navigator.clipboard.writeText(activeRequestId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const safeDetails = sanitizeErrorTrace(technicalDetails);

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="error-dialog-title"
      >
        <div className={styles.header}>
          <div className={styles.iconCircle}>
            <AlertCircle size={22} />
          </div>
          <div className={styles.titleGroup}>
            <h2 id="error-dialog-title" className={styles.title}>
              {title}
            </h2>
            <div className={styles.requestIdRow}>
              <span className={styles.requestIdBadge}>Request ID: {activeRequestId}</span>
              <button className={styles.copyBtn} onClick={handleCopyRequestId}>
                {copied ? <Check size={12} color="var(--accent-green)" /> : <Copy size={12} />}
                <span>{copied ? "Copied!" : "Copy"}</span>
              </button>
            </div>
          </div>
          <button
            style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer" }}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>

        <p className={styles.description}>{message}</p>

        {technicalDetails && (
          <>
            <button
              className={styles.accordionToggle}
              onClick={() => setShowDetails(!showDetails)}
            >
              <span>Technical Diagnostics & Stack Trace</span>
              {showDetails ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
            {showDetails && <pre className={`${styles.techDetails} mono`}>{safeDetails}</pre>}
          </>
        )}

        <div className={styles.recoverySection}>
          <div className={styles.recoveryLabel}>Actionable Recovery Options</div>
          <div className={styles.actionGrid}>
            {onRetry && (
              <Button
                variant="primary"
                size="sm"
                icon={<RotateCcw size={14} />}
                onClick={() => {
                  onRetry();
                  onClose();
                }}
              >
                Retry Stage / Action
              </Button>
            )}

            {onResume && (
              <Button
                variant="secondary"
                size="sm"
                icon={<Play size={14} />}
                onClick={() => {
                  onResume();
                  onClose();
                }}
              >
                Resume Migration
              </Button>
            )}

            {onDownloadLogs && (
              <Button
                variant="secondary"
                size="sm"
                icon={<Download size={14} />}
                onClick={onDownloadLogs}
              >
                Download Logs
              </Button>
            )}

            {onViewSql && (
              <Button
                variant="secondary"
                size="sm"
                icon={<FileCode size={14} />}
                onClick={onViewSql}
              >
                View SQL
              </Button>
            )}

            {onReportBug && (
              <Button
                variant="ghost"
                size="sm"
                icon={<Bug size={14} />}
                onClick={onReportBug}
              >
                Report Issue
              </Button>
            )}

            <Button variant="ghost" size="sm" onClick={onClose}>
              Dismiss
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
