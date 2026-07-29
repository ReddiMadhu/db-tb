"use client";

import React, { useState } from "react";
import { Search, Download, Filter, ShieldCheck } from "lucide-react";
import Button from "@/components/ui/Button";
import styles from "./StructuredLogViewer.module.css";

export interface LogEntry {
  id: string;
  timestamp: string;
  stage: string;
  severity: "INFO" | "WARN" | "ERROR";
  component: string;
  message: string;
  durationMs: number;
  correlationId: string;
}

const SAMPLE_LOGS: LogEntry[] = [
  {
    id: "log-101",
    timestamp: "13:42:01.102",
    stage: "Stage 1: XML Parse",
    severity: "INFO",
    component: "TableauXmlParser",
    message: "Unpacking .twbx archive container and extracting DOM tree",
    durationMs: 142,
    correlationId: "req-8F93A2",
  },
  {
    id: "log-102",
    timestamp: "13:42:01.245",
    stage: "Stage 2: TOM Extraction",
    severity: "INFO",
    component: "TomNormalizer",
    message: "Normalized 42 calc field formulas to snake_case identifier rules",
    durationMs: 98,
    correlationId: "req-8F93A2",
  },
  {
    id: "log-103",
    timestamp: "13:42:02.310",
    stage: "Stage 4: SQL Transpile",
    severity: "INFO",
    component: "SqlGlotTranspiler",
    message: "Transpiled Tableau LOD expression FIXED [Region] : SUM([Sales]) to Spark SQL OVER window",
    durationMs: 310,
    correlationId: "req-8F93A2",
  },
  {
    id: "log-104",
    timestamp: "13:42:03.450",
    stage: "Stage 7: Validation",
    severity: "INFO",
    component: "AstValidator",
    message: "6-Tier AST Validation sweep completed with 100% compliance",
    durationMs: 95,
    correlationId: "req-8F93A2",
  },
  {
    id: "log-105",
    timestamp: "13:42:04.120",
    stage: "Stage 9: Workspace Creds",
    severity: "INFO",
    component: "DatabricksWorkspaceClient",
    message: "Verified SQL Warehouse a1b2c3d4e5f67890 connection with token dapi-••••••••••••",
    durationMs: 45,
    correlationId: "req-8F93A2",
  },
];

export default function StructuredLogViewer() {
  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");

  const filteredLogs = SAMPLE_LOGS.filter((l) => {
    const matchesSearch =
      l.message.toLowerCase().includes(search.toLowerCase()) ||
      l.component.toLowerCase().includes(search.toLowerCase()) ||
      l.stage.toLowerCase().includes(search.toLowerCase()) ||
      l.correlationId.toLowerCase().includes(search.toLowerCase());

    const matchesSeverity = severityFilter === "ALL" || l.severity === severityFilter;

    return matchesSearch && matchesSeverity;
  });

  const handleExportLogs = () => {
    const jsonStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(filteredLogs, null, 2));
    const dlAnchor = document.createElement("a");
    dlAnchor.setAttribute("href", jsonStr);
    dlAnchor.setAttribute("download", `lakeshift_logs_${Date.now()}.json`);
    dlAnchor.click();
  };

  return (
    <div className={styles.container}>
      <div className={styles.filterRow}>
        <div className={styles.searchBox}>
          <Search size={16} style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-tertiary)" }} />
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Search logs by message, stage, component, or correlation ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            style={{
              padding: "0.55rem 0.8rem",
              background: "var(--bg-card)",
              border: "1px solid var(--border-default)",
              borderRadius: "6px",
              color: "#fff",
              fontSize: "0.85rem",
            }}
          >
            <option value="ALL">All Severities</option>
            <option value="INFO">INFO</option>
            <option value="WARN">WARN</option>
            <option value="ERROR">ERROR</option>
          </select>

          <Button variant="secondary" size="sm" icon={<Download size={14} />} onClick={handleExportLogs}>
            Export Logs
          </Button>
        </div>
      </div>

      <table className={styles.logTable}>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Severity</th>
            <th>Stage</th>
            <th>Component</th>
            <th>Message</th>
            <th>Duration</th>
            <th>Correlation ID</th>
          </tr>
        </thead>
        <tbody>
          {filteredLogs.map((log) => (
            <tr key={log.id}>
              <td className="mono" style={{ color: "var(--text-tertiary)", fontSize: "0.75rem" }}>
                {log.timestamp}
              </td>
              <td>
                <span
                  className={
                    log.severity === "INFO"
                      ? styles.severityInfo
                      : log.severity === "WARN"
                      ? styles.severityWarn
                      : styles.severityError
                  }
                >
                  {log.severity}
                </span>
              </td>
              <td style={{ fontWeight: 500 }}>{log.stage}</td>
              <td className="mono" style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                {log.component}
              </td>
              <td>{log.message}</td>
              <td className="mono" style={{ fontSize: "0.75rem" }}>
                {log.durationMs}ms
              </td>
              <td className="mono" style={{ fontSize: "0.75rem", color: "var(--accent-orange)" }}>
                {log.correlationId}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
