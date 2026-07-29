"use client";

import React, { useState } from "react";
import { ArrowRightLeft, X, CheckCircle2, AlertTriangle, ShieldCheck, BarChart3, Database } from "lucide-react";
import Button from "@/components/ui/Button";
import Badge from "@/components/ui/Badge";
import styles from "./DashboardComparisonModal.module.css";

export interface DashboardComparisonModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function DashboardComparisonModal({ isOpen, onClose }: DashboardComparisonModalProps) {
  const [activeTab, setActiveTab] = useState<"sideBySide" | "semantic">("semantic");

  if (!isOpen) return null;

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className={styles.header}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <ArrowRightLeft size={20} color="var(--accent-orange)" />
            <h2 className={styles.title}>Tableau vs. Databricks Lakeview Comparison & Semantic Validation</h2>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <Button
              variant={activeTab === "semantic" ? "primary" : "secondary"}
              size="sm"
              onClick={() => setActiveTab("semantic")}
            >
              Semantic Metrics
            </Button>
            <Button
              variant={activeTab === "sideBySide" ? "primary" : "secondary"}
              size="sm"
              onClick={() => setActiveTab("sideBySide")}
            >
              Side-by-Side Code
            </Button>
            <button className={styles.closeBtn} onClick={onClose}>
              <X size={20} />
            </button>
          </div>
        </div>

        {activeTab === "semantic" ? (
          <div style={{ padding: "1.5rem", display: "flex", flexDirection: "column", gap: "1.25rem", overflowY: "auto" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1rem" }}>
              <div className={styles.semanticCard}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>SQL Equivalence Score</div>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--accent-green)" }}>99.4%</div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>AST Query transpiled with sqlglot</div>
              </div>

              <div className={styles.semanticCard}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>Row-Count Parity</div>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--accent-green)" }}>100% Match</div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>14,280 / 14,280 rows validated</div>
              </div>

              <div className={styles.semanticCard}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>Aggregation Accuracy</div>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--accent-green)" }}>0 Mismatches</div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>LOD & Table Calcs compiled to Window functions</div>
              </div>

              <div className={styles.semanticCard}>
                <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>Visual Compatibility</div>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--accent-orange)" }}>98.0%</div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>6-column grid projection</div>
              </div>
            </div>

            <div className={styles.semanticCard}>
              <h3 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.75rem" }}>
                Semantic Validation Audit Details
              </h3>
              
              <div className={styles.metricRow}>
                <span>Aggregation Function Mapping (SUM, AVG, COUNTD)</span>
                <span style={{ color: "var(--accent-green)", fontWeight: 600 }}>100% Verified</span>
              </div>
              <div className={styles.metricRow}>
                <span>Filter & Parameter Transpilation</span>
                <span style={{ color: "var(--accent-green)", fontWeight: 600 }}>100% Verified</span>
              </div>
              <div className={styles.metricRow}>
                <span>Level of Detail (FIXED / INCLUDE / EXCLUDE)</span>
                <span style={{ color: "var(--accent-green)", fontWeight: 600 }}>Transpiled to OVER (PARTITION BY)</span>
              </div>
              <div className={styles.metricRow}>
                <span>Unsupported Tableau Features</span>
                <span style={{ color: "var(--accent-amber)", fontWeight: 600 }}>0 Blocking (1 Warning: Legacy Story Points mapped to Lakeview Tabs)</span>
              </div>
            </div>
          </div>
        ) : (
          <div className={styles.splitGrid}>
            {/* Left Pane: Tableau */}
            <div className={styles.pane}>
              <div className={styles.paneTitle} style={{ color: "var(--accent-orange)" }}>
                <BarChart3 size={18} />
                <span>Source Tableau Workbook (.twb)</span>
              </div>

              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginBottom: "0.35rem" }}>
                  Tableau Expression Formula:
                </div>
                <pre className={`${styles.codeBox} mono`}>
                  {`// Tableau LOD Formula
{ FIXED [Region] : SUM([Sales]) }

// Tableau Table Calc
RUNNING_SUM(SUM([Sales]))`}
                </pre>
              </div>
            </div>

            {/* Right Pane: Lakeview */}
            <div className={styles.pane}>
              <div className={styles.paneTitle} style={{ color: "var(--accent-green)" }}>
                <Database size={18} />
                <span>Target Databricks Lakeview AST</span>
              </div>

              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginBottom: "0.35rem" }}>
                  Transpiled Spark SQL Query:
                </div>
                <pre className={`${styles.codeBox} mono`}>
                  {`-- Databricks Spark SQL Window Function
SUM(Sales) OVER (PARTITION BY Region) AS Region_Sales,

-- Running Total Window Frame
SUM(SUM(Sales)) OVER (
  ORDER BY Order_Date 
  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS Running_Sales`}
                </pre>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
