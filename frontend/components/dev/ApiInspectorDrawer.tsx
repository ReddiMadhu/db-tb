"use client";

import React, { useState } from "react";
import { Terminal, X, Download, ShieldCheck } from "lucide-react";
import Button from "@/components/ui/Button";
import styles from "./ApiInspectorDrawer.module.css";

export interface ApiInspectorDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

// Redact sensitive headers/tokens
function sanitizeObject<T>(obj: T): T {
  if (!obj) return obj;
  const str = JSON.stringify(obj);
  const sanitizedStr = str
    .replace(/(dapi-[a-zA-Z0-9_-]{10,})/g, "dapi-••••••••••••")
    .replace(/("token"|"password"|"api_key"|"authorization"|"key")\s*:\s*"[^"]+"/gi, '$1:"••••••••"');
  try {
    return JSON.parse(sanitizedStr);
  } catch {
    return obj;
  }
}

export default function ApiInspectorDrawer({ isOpen, onClose }: ApiInspectorDrawerProps) {
  const [activeTab, setActiveTab] = useState<"diagnostics" | "network" | "queryCache" | "flags">("diagnostics");

  if (!isOpen) return null;

  const sampleDiagnostics = {
    activeJobs: 1,
    queryCacheKeys: ["migrations", "migration-status-job-1", "databricks-connections"],
    apiRetries: 0,
    performanceTimings: {
      domComplete: "320ms",
      apiAverageLatency: "48ms",
      astParseDuration: "142ms",
    },
    memoryUsage: typeof window !== "undefined" && (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory
      ? `${Math.round(((performance as unknown as { memory: { usedJSHeapSize: number } }).memory.usedJSHeapSize) / 1024 / 1024)} MB`
      : "34 MB (Heap)",
    featureFlags: {
      enableAiFallbackCompiler: true,
      enable6TierAstValidation: true,
      enableLakeviewRendererV2: true,
      enableDabExport: true,
    },
  };

  const sampleNetworkLogs = [
    {
      id: "req-1",
      method: "POST",
      endpoint: "/api/v1/migrations/upload",
      status: 200,
      durationMs: 340,
      headers: { "Content-Type": "multipart/form-data" },
      payload: { filename: "Executive_Dashboard.twbx" },
      response: { success: true, job_uuid: "8f93a2b1-4c5d-6e7f-8a9b-0c1d2e3f4a5b" },
    },
    {
      id: "req-2",
      method: "POST",
      endpoint: "/api/v1/migrations/8f93a2b1/execute",
      status: 200,
      durationMs: 820,
      headers: { "Content-Type": "application/json" },
      payload: { job_uuid: "8f93a2b1" },
      response: { success: true, message: "Pipeline completed through Stage 10" },
    },
  ];

  const handleDownloadDiagnostics = () => {
    const timestamp = Date.now();
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(sanitizeObject({
      diagnostics: sampleDiagnostics,
      network: sampleNetworkLogs,
      exportedAt: new Date().toISOString(),
    }), null, 2));
    const dlAnchorElem = document.createElement("a");
    dlAnchorElem.setAttribute("href", dataStr);
    dlAnchorElem.setAttribute("download", `t2d_diagnostics_${timestamp}.json`);
    dlAnchorElem.click();
  };

  return (
    <div className={styles.drawerBackdrop} onClick={onClose}>
      <div className={styles.drawer} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <div className={styles.titleGroup}>
            <Terminal size={18} color="var(--accent-orange)" />
            <h2 className={styles.title}>Developer Diagnostics Panel</h2>
          </div>
          <button className={styles.closeBtn} onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className={styles.tabBar}>
          <button
            className={`${styles.tab} ${activeTab === "diagnostics" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("diagnostics")}
          >
            System Metrics
          </button>
          <button
            className={`${styles.tab} ${activeTab === "network" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("network")}
          >
            API Inspector
          </button>
          <button
            className={`${styles.tab} ${activeTab === "queryCache" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("queryCache")}
          >
            Query Cache
          </button>
          <button
            className={`${styles.tab} ${activeTab === "flags" ? styles.activeTab : ""}`}
            onClick={() => setActiveTab("flags")}
          >
            Feature Flags
          </button>
        </div>

        <div className={styles.content}>
          {activeTab === "diagnostics" && (
            <>
              <div className={styles.metricGrid}>
                <div className={styles.metricCard}>
                  <div className={styles.metricVal}>{sampleDiagnostics.memoryUsage}</div>
                  <div className={styles.metricLbl}>JS Heap Memory</div>
                </div>
                <div className={styles.metricCard}>
                  <div className={styles.metricVal} style={{ color: "var(--accent-green)" }}>
                    {sampleDiagnostics.performanceTimings.apiAverageLatency}
                  </div>
                  <div className={styles.metricLbl}>Avg API Latency</div>
                </div>
                <div className={styles.metricCard}>
                  <div className={styles.metricVal} style={{ color: "var(--accent-info)" }}>
                    {sampleDiagnostics.activeJobs}
                  </div>
                  <div className={styles.metricLbl}>Active Jobs</div>
                </div>
                <div className={styles.metricCard}>
                  <div className={styles.metricVal} style={{ color: "var(--accent-purple)" }}>
                    {sampleDiagnostics.apiRetries}
                  </div>
                  <div className={styles.metricLbl}>API Retries</div>
                </div>
              </div>

              <h3>Performance Timings</h3>
              <pre className={`${styles.jsonBox} mono`}>
                {JSON.stringify(sampleDiagnostics.performanceTimings, null, 2)}
              </pre>
            </>
          )}

          {activeTab === "network" && (
            <div>
              <h3>Recent API Request Logs (Sanitized)</h3>
              <p style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginBottom: "0.75rem" }}>
                Credentials and authorization tokens are automatically redacted.
              </p>
              <pre className={`${styles.jsonBox} mono`}>
                {JSON.stringify(sanitizeObject(sampleNetworkLogs), null, 2)}
              </pre>
            </div>
          )}

          {activeTab === "queryCache" && (
            <div>
              <h3>TanStack React Query Active Cache Keys</h3>
              <pre className={`${styles.jsonBox} mono`}>
                {JSON.stringify(sampleDiagnostics.queryCacheKeys, null, 2)}
              </pre>
            </div>
          )}

          {activeTab === "flags" && (
            <div>
              <h3>Platform Environment Feature Flags</h3>
              <pre className={`${styles.jsonBox} mono`}>
                {JSON.stringify(sampleDiagnostics.featureFlags, null, 2)}
              </pre>
            </div>
          )}
        </div>

        <div className={styles.footer}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.75rem", color: "var(--accent-green)" }}>
            <ShieldCheck size={16} />
            <span>Enterprise Credentials Redacted</span>
          </div>

          <Button
            variant="primary"
            size="sm"
            icon={<Download size={14} />}
            onClick={handleDownloadDiagnostics}
          >
            Download JSON
          </Button>
        </div>
      </div>
    </div>
  );
}
