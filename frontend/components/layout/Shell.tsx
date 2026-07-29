"use client";

import React, { useState, useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Sidebar from "./Sidebar";
import Header from "./Header";
import Inspector from "./Inspector";
import CommandPalette from "./CommandPalette";
import ErrorBoundary from "./ErrorBoundary";
import { ToastProvider } from "@/components/ui/ToastProvider";
import { AsyncOperationProvider } from "@/components/providers/AsyncOperationProvider";
import ApiInspectorDrawer from "@/components/dev/ApiInspectorDrawer";
import styles from "./Shell.module.css";

export default function Shell({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  const [devInspectorOpen, setDevInspectorOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Toggle Dev Diagnostics Panel with Cmd+Shift+D / Ctrl+Shift+D
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "d") {
        e.preventDefault();
        setDevInspectorOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <AsyncOperationProvider>
            <div className={styles.shell}>
              <Sidebar />
              <div className={styles.mainWrapper}>
                <Header />
                <main className={styles.contentArea}>{children}</main>
              </div>
              <Inspector />
              <CommandPalette />
              <ApiInspectorDrawer
                isOpen={devInspectorOpen}
                onClose={() => setDevInspectorOpen(false)}
              />
            </div>
          </AsyncOperationProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
