"use client";

import React, { createContext, useContext, useState, useCallback } from "react";
import LoadingOverlay from "@/components/modals/LoadingOverlay";
import SuccessDialog from "@/components/modals/SuccessDialog";
import ErrorDialog from "@/components/modals/ErrorDialog";
import { useToast } from "@/components/ui/ToastProvider";

export interface AsyncOpState {
  id: string;
  type: "overlay" | "toast" | "silent";
  title: string;
  stageText: string;
  taskDescription: string;
  progressPercent: number;
  isLoading: boolean;
  onCancel?: () => void;
}

interface AsyncOpContextType {
  startOperation: (options: {
    title: string;
    stageText?: string;
    taskDescription?: string;
    type?: "overlay" | "toast" | "silent";
    onCancel?: () => void;
  }) => string;
  updateProgress: (opId: string, percent: number, stageText?: string, taskDescription?: string) => void;
  finishSuccess: (opId: string, options: { title: string; description: string; details?: Array<{ label: string; value: string }>; primaryActionLabel?: string; onPrimaryAction?: () => void }) => void;
  finishError: (opId: string, options: { title?: string; message: string; technicalDetails?: string; onRetry?: () => void }) => void;
}

const AsyncOpContext = createContext<AsyncOpContextType | undefined>(undefined);

export function AsyncOperationProvider({ children }: { children: React.ReactNode }) {
  const { success, error } = useToast();
  const [activeOp, setActiveOp] = useState<AsyncOpState | null>(null);

  // Milestone Success Dialog state
  const [successModal, setSuccessModal] = useState<{
    isOpen: boolean;
    title: string;
    description: string;
    details?: Array<{ label: string; value: string }>;
    primaryActionLabel?: string;
    onPrimaryAction?: () => void;
  } | null>(null);

  // Error Recovery Dialog state
  const [errorModal, setErrorModal] = useState<{
    isOpen: boolean;
    title?: string;
    message: string;
    technicalDetails?: string;
    onRetry?: () => void;
  } | null>(null);

  const startOperation = useCallback(
    ({
      title,
      stageText = "Initializing...",
      taskDescription = "Preparing operation...",
      type = "overlay",
      onCancel,
    }: {
      title: string;
      stageText?: string;
      taskDescription?: string;
      type?: "overlay" | "toast" | "silent";
      onCancel?: () => void;
    }) => {
      const opId = `op-${Date.now()}`;
      setActiveOp({
        id: opId,
        type,
        title,
        stageText,
        taskDescription,
        progressPercent: 5,
        isLoading: true,
        onCancel,
      });
      return opId;
    },
    []
  );

  const updateProgress = useCallback(
    (opId: string, percent: number, stageText?: string, taskDescription?: string) => {
      setActiveOp((prev) => {
        if (!prev || prev.id !== opId) return prev;
        return {
          ...prev,
          progressPercent: percent,
          stageText: stageText || prev.stageText,
          taskDescription: taskDescription || prev.taskDescription,
        };
      });
    },
    []
  );

  const finishSuccess = useCallback(
    (
      opId: string,
      options: {
        title: string;
        description: string;
        details?: Array<{ label: string; value: string }>;
        primaryActionLabel?: string;
        onPrimaryAction?: () => void;
      }
    ) => {
      setActiveOp(null);
      setSuccessModal({
        isOpen: true,
        title: options.title,
        description: options.description,
        details: options.details,
        primaryActionLabel: options.primaryActionLabel,
        onPrimaryAction: options.onPrimaryAction,
      });
    },
    []
  );

  const finishError = useCallback(
    (
      opId: string,
      options: {
        title?: string;
        message: string;
        technicalDetails?: string;
        onRetry?: () => void;
      }
    ) => {
      setActiveOp(null);
      setErrorModal({
        isOpen: true,
        title: options.title || "Operation Failed",
        message: options.message,
        technicalDetails: options.technicalDetails,
        onRetry: options.onRetry,
      });
    },
    []
  );

  return (
    <AsyncOpContext.Provider value={{ startOperation, updateProgress, finishSuccess, finishError }}>
      {children}

      {/* Global Progress Overlay */}
      {activeOp && activeOp.type === "overlay" && (
        <LoadingOverlay
          isOpen={true}
          title={activeOp.title}
          stageText={activeOp.stageText}
          taskDescription={activeOp.taskDescription}
          progressPercent={activeOp.progressPercent}
          onCancel={() => {
            if (activeOp.onCancel) activeOp.onCancel();
            setActiveOp(null);
          }}
        />
      )}

      {/* Global Milestone Success Dialog */}
      {successModal && (
        <SuccessDialog
          isOpen={successModal.isOpen}
          title={successModal.title}
          description={successModal.description}
          details={successModal.details}
          primaryActionLabel={successModal.primaryActionLabel}
          onPrimaryAction={successModal.onPrimaryAction}
          onClose={() => setSuccessModal(null)}
        />
      )}

      {/* Global Error Recovery Dialog */}
      {errorModal && (
        <ErrorDialog
          isOpen={errorModal.isOpen}
          title={errorModal.title}
          message={errorModal.message}
          technicalDetails={errorModal.technicalDetails}
          onRetry={errorModal.onRetry}
          onClose={() => setErrorModal(null)}
        />
      )}
    </AsyncOpContext.Provider>
  );
}

export function useAsyncOperation() {
  const context = useContext(AsyncOpContext);
  if (!context) {
    throw new Error("useAsyncOperation must be used within AsyncOperationProvider");
  }
  return context;
}
