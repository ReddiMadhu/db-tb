"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import Inspector from "./Inspector";
import CommandPalette from "./CommandPalette";
import styles from "./Shell.module.css";

export default function Shell({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <div className={styles.shell}>
        <Sidebar />
        <div className={styles.mainWrapper}>
          <Header />
          <main className={styles.contentArea}>{children}</main>
        </div>
        <Inspector />
        <CommandPalette />
      </div>
    </QueryClientProvider>
  );
}
