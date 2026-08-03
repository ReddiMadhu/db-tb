"use client";

import React, { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Sidebar from "./Sidebar";
import Header from "./Header";
import CommandPalette from "./CommandPalette";
import ErrorBoundary from "./ErrorBoundary";
import { ToastProvider } from "@/components/ui/ToastProvider";
import { AsyncOperationProvider } from "@/components/providers/AsyncOperationProvider";
import styles from "./Shell.module.css";

export default function Shell({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

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
              <CommandPalette />
            </div>
          </AsyncOperationProvider>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
