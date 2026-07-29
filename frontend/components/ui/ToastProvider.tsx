"use client";

import React, { createContext, useContext, useState, useCallback } from "react";
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from "lucide-react";
import styles from "./ToastProvider.module.css";

export type ToastType = "success" | "error" | "warning" | "info";

export interface ToastItem {
  id: string;
  type: ToastType;
  title?: string;
  message: string;
  duration?: number;
}

interface ToastContextType {
  toast: (options: { type?: ToastType; title?: string; message: string; duration?: number }) => void;
  success: (message: string, title?: string) => void;
  error: (message: string, title?: string) => void;
  warning: (message: string, title?: string) => void;
  info: (message: string, title?: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    ({ type = "info", title, message, duration = 4000 }: { type?: ToastType; title?: string; message: string; duration?: number }) => {
      const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      const newItem: ToastItem = { id, type, title, message, duration };
      
      setToasts((prev) => [...prev.slice(-4), newItem]);

      if (duration > 0) {
        setTimeout(() => {
          removeToast(id);
        }, duration);
      }
    },
    [removeToast]
  );

  const success = useCallback((message: string, title?: string) => toast({ type: "success", title, message }), [toast]);
  const error = useCallback((message: string, title?: string) => toast({ type: "error", title, message }), [toast]);
  const warning = useCallback((message: string, title?: string) => toast({ type: "warning", title, message }), [toast]);
  const info = useCallback((message: string, title?: string) => toast({ type: "info", title, message }), [toast]);

  return (
    <ToastContext.Provider value={{ toast, success, error, warning, info }}>
      {children}
      <div className={styles.toastContainer} aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`${styles.toast} ${styles[t.type]}`}>
            <div className={styles.icon}>
              {t.type === "success" && <CheckCircle2 size={18} color="var(--accent-green)" />}
              {t.type === "error" && <AlertCircle size={18} color="var(--accent-red)" />}
              {t.type === "warning" && <AlertTriangle size={18} color="var(--accent-amber)" />}
              {t.type === "info" && <Info size={18} color="var(--accent-orange)" />}
            </div>

            <div className={styles.body}>
              {t.title && <div className={styles.title}>{t.title}</div>}
              <div className={styles.message}>{t.message}</div>
            </div>

            <button className={styles.closeBtn} onClick={() => removeToast(t.id)} aria-label="Close notification">
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
