"use client";

import { useState } from "react";
import { Info, MessageSquare, History, CheckCircle2, ShieldCheck } from "lucide-react";
import { useUIStore, useSelectionStore } from "@/lib/store";
import styles from "./Inspector.module.css";

export default function Inspector() {
  const { inspectorOpen } = useUIStore();
  const { selectedAssetType, selectedAssetId } = useSelectionStore();
  const [activeTab, setActiveTab] = useState<"props" | "comments" | "history">("props");

  if (!inspectorOpen) return null;

  return (
    <aside className={styles.inspector}>
      <div className={styles.header}>
        <span>Inspector</span>
        <ShieldCheck size={16} color="var(--accent-green)" />
      </div>

      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === "props" ? styles.active : ""}`}
          onClick={() => setActiveTab("props")}
        >
          Properties
        </button>
        <button
          className={`${styles.tab} ${activeTab === "comments" ? styles.active : ""}`}
          onClick={() => setActiveTab("comments")}
        >
          Comments
        </button>
        <button
          className={`${styles.tab} ${activeTab === "history" ? styles.active : ""}`}
          onClick={() => setActiveTab("history")}
        >
          History
        </button>
      </div>

      <div className={styles.content}>
        {activeTab === "props" && (
          <>
            {selectedAssetId ? (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>{selectedAssetType || "Entity"} Details</div>
                <div className={styles.propRow}>
                  <span className={styles.propLabel}>ID / Name</span>
                  <span className={`${styles.propValue} mono`}>{selectedAssetId}</span>
                </div>
                <div className={styles.propRow}>
                  <span className={styles.propLabel}>Type</span>
                  <span className={styles.propValue}>{selectedAssetType}</span>
                </div>
                <div className={styles.propRow}>
                  <span className={styles.propLabel}>Status</span>
                  <span className={styles.propValue} style={{ color: "var(--accent-green)", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
                    <CheckCircle2 size={12} /> Validated
                  </span>
                </div>
                <div className={styles.propRow}>
                  <span className={styles.propLabel}>Target Platform</span>
                  <span className={styles.propValue}>Databricks AI/BI</span>
                </div>
              </div>
            ) : (
              <div className={styles.section}>
                <div className={styles.sectionTitle}>Overview</div>
                <div className={styles.propRow}>
                  <span className={styles.propLabel}>Target Engine</span>
                  <span className={styles.propValue}>Databricks Spark SQL</span>
                </div>
                <div className={styles.propRow}>
                  <span className={styles.propLabel}>Target AST</span>
                  <span className={styles.propValue}>Lakeview 24_json_schema</span>
                </div>
                <div className={styles.propRow}>
                  <span className={styles.propLabel}>Validation Tiers</span>
                  <span className={styles.propValue}>6-Tier Engine</span>
                </div>
                <div className={styles.propRow}>
                  <span className={styles.propLabel}>Layout Grid</span>
                  <span className={styles.propValue}>6-Column System</span>
                </div>

                <div className={styles.emptyState}>
                  <Info size={24} />
                  <span>Select any dataset, worksheet, widget, or expression to inspect properties.</span>
                </div>
              </div>
            )}
          </>
        )}

        {activeTab === "comments" && (
          <div className={styles.emptyState}>
            <MessageSquare size={24} />
            <span>No comments yet. Team review comments will appear here.</span>
          </div>
        )}

        {activeTab === "history" && (
          <div className={styles.emptyState}>
            <History size={24} />
            <span>No version history. Run pipeline executions to generate audit history.</span>
          </div>
        )}
      </div>
    </aside>
  );
}
