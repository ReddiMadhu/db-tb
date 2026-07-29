"use client";

import React, { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronUp, Loader2, AlertTriangle, Clock } from "lucide-react";
import Badge from "@/components/ui/Badge";
import styles from "./PipelineStageInspector.module.css";

export interface StageData {
  id: number;
  name: string;
  status: "COMPLETED" | "RUNNING" | "QUEUED" | "FAILED";
  durationMs: number;
  inputSummary: string;
  outputSummary: string;
  logs: string[];
  warnings?: string[];
  generatedCode?: string;
}

const DEFAULT_STAGES: StageData[] = [
  {
    id: 1,
    name: "Tableau XML Parsing & DOM Indexing",
    status: "COMPLETED",
    durationMs: 142,
    inputSummary: "Workbook.twbx archive extracted (.twb XML DOM tree parsed)",
    outputSummary: "Parsed 14 worksheets, 3 dashboards, 6 datasources, 42 calculated fields",
    logs: [
      "[INFO] 13:42:01 Unpacking .twbx zip container...",
      "[INFO] 13:42:01 Extracting workbooks/Executive_Dashboard.twb XML payload",
      "[SUCCESS] 13:42:01 XML DOM tree loaded into memory (42KB)",
    ],
  },
  {
    id: 2,
    name: "Tableau Object Model (TOM) Extraction",
    status: "COMPLETED",
    durationMs: 98,
    inputSummary: "Raw XML DOM nodes",
    outputSummary: "TOM JSON structure generated with dataset aliases and join paths",
    logs: [
      "[INFO] 13:42:01 Normalizing Tableau calc field names: [Order Date] -> order_date",
      "[SUCCESS] 13:42:02 Extracted 6 connection nodes & 14 visual encodings",
    ],
  },
  {
    id: 3,
    name: "Calculated Field Dependency Graph",
    status: "COMPLETED",
    durationMs: 76,
    inputSummary: "42 raw Tableau formulas",
    outputSummary: "Directed Acyclic Graph (DAG) constructed for Level of Detail & Table Calcs",
    logs: [
      "[INFO] 13:42:02 Resolving LOD expression dependencies: FIXED [Region] : SUM([Sales])",
      "[SUCCESS] 13:42:02 DAG topological order resolved (0 cycles detected)",
    ],
  },
  {
    id: 4,
    name: "Spark SQL Transpilation (sqlglot AST)",
    status: "COMPLETED",
    durationMs: 310,
    inputSummary: "Tableau formula syntax tree",
    outputSummary: "Databricks Spark SQL 3.5 queries transpiled with window functions",
    logs: [
      "[INFO] 13:42:02 Transpiling RUNNING_SUM(SUM([Sales])) -> SUM(SUM(Sales)) OVER ()",
      "[SUCCESS] 13:42:03 Transpiled 42 SQL expressions cleanly",
    ],
    generatedCode: `SELECT \n  EXTRACT(MONTH FROM Order_Date) AS Month,\n  SUM(Sales) OVER (PARTITION BY Region ORDER BY Order_Date) AS Running_Sales\nFROM orders\nGROUP BY 1, 2;`,
  },
  {
    id: 5,
    name: "UBIM Universal Intermediate Normalization",
    status: "COMPLETED",
    durationMs: 115,
    inputSummary: "TOM & Transpiled SQL",
    outputSummary: "UBIM model conforming to LakeShift intermediate representation",
    logs: [
      "[INFO] 13:42:03 Mapping Tableau Marks (Bar, Line, Text) to Lakeview Visual Types",
      "[SUCCESS] 13:42:03 UBIM model generated with 12 widget specs",
    ],
  },
  {
    id: 6,
    name: "Lakeview AST Dashboard Generation",
    status: "COMPLETED",
    durationMs: 180,
    inputSummary: "UBIM Model",
    outputSummary: "Databricks Lakeview Dashboard JSON (.lvdash.json)",
    logs: [
      "[INFO] 13:42:03 Formatting 6-column grid layout coordinates",
      "[SUCCESS] 13:42:04 Lakeview dashboard AST constructed with version 1/2/3 widget schemas",
    ],
    generatedCode: `{\n  "version": 1,\n  "pages": [\n    {\n      "name": "Executive Overview",\n      "layout": [\n        { "widget_id": "w1", "x": 0, "y": 0, "width": 6, "height": 4 }\n      ]\n    }\n  ]\n}`,
  },
  {
    id: 7,
    name: "Automated 6-Tier AST Validation Sweep",
    status: "COMPLETED",
    durationMs: 95,
    inputSummary: "Lakeview AST JSON",
    outputSummary: "0 schema errors, 100% compliance against 24_json_schema.json",
    logs: [
      "[INFO] 13:42:04 Checking jsonschema validation constraints",
      "[INFO] 13:42:04 Checking layout bounds (x + width <= 6)",
      "[SUCCESS] 13:42:04 All 6 validation tiers passed successfully",
    ],
  },
  {
    id: 8,
    name: "Databricks Asset Bundle Packaging",
    status: "COMPLETED",
    durationMs: 64,
    inputSummary: "Lakeview AST & Workspace Config",
    outputSummary: "databricks.yml bundle configuration generated",
    logs: [
      "[INFO] 13:42:04 Generating databricks.yml target resource manifest",
      "[SUCCESS] 13:42:04 Asset bundle created",
    ],
  },
  {
    id: 9,
    name: "Target Workspace Credential Verification",
    status: "COMPLETED",
    durationMs: 45,
    inputSummary: "Databricks Workspace Connection (AWS)",
    outputSummary: "SQL Warehouse ID a1b2c3d4e5f67890 active (38ms latency)",
    logs: [
      "[INFO] 13:42:04 Ping SQL Warehouse host: https://dbc-prod-az.cloud.databricks.com",
      "[SUCCESS] 13:42:04 Credentials verified",
    ],
  },
  {
    id: 10,
    name: "Databricks REST API Publication",
    status: "COMPLETED",
    durationMs: 240,
    inputSummary: "Lakeview Bundle Payload",
    outputSummary: "Published live to Databricks Lakeview workspace",
    logs: [
      "[INFO] 13:42:04 Executing REST API POST /api/2.0/lakeview/dashboards",
      "[SUCCESS] 13:42:05 Published! Workspace Dashboard URL generated.",
    ],
  },
];

export default function PipelineStageInspector() {
  const [expandedId, setExpandedId] = useState<number | null>(4); // Stage 4 open by default

  const toggleExpand = (id: number) => {
    setExpandedId(expandedId === id ? null : id);
  };

  return (
    <div className={styles.container}>
      <h3 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
        10-Stage Pipeline Inspector
      </h3>
      <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
        Expand any stage to inspect input artifacts, transpiled SQL, output AST, real-time logs, and execution duration.
      </p>

      {DEFAULT_STAGES.map((s) => {
        const isOpen = expandedId === s.id;
        return (
          <div key={s.id} className={styles.stageCard}>
            <div className={styles.stageHeader} onClick={() => toggleExpand(s.id)}>
              <div className={styles.titleGroup}>
                <span className={`${styles.stageNumber} mono`}>Stage {s.id}</span>
                {s.status === "COMPLETED" && <CheckCircle2 size={16} color="var(--accent-green)" />}
                {s.status === "RUNNING" && <Loader2 size={16} className="spin" color="var(--accent-orange)" />}
                {s.status === "FAILED" && <AlertTriangle size={16} color="var(--accent-red)" />}
                <span className={styles.stageName}>{s.name}</span>
              </div>

              <div className={styles.rightGroup}>
                <span className={`${styles.duration} mono`}>
                  <Clock size={12} style={{ display: "inline", marginRight: "0.25rem" }} />
                  {s.durationMs}ms
                </span>
                <Badge status={s.status} />
                {isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </div>
            </div>

            {isOpen && (
              <div className={styles.stageBody}>
                <div>
                  <div className={styles.sectionTitle}>Input Artifact</div>
                  <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>{s.inputSummary}</div>
                </div>

                <div>
                  <div className={styles.sectionTitle}>Output Summary</div>
                  <div style={{ fontSize: "0.8125rem", color: "var(--accent-green)", fontWeight: 500 }}>
                    {s.outputSummary}
                  </div>
                </div>

                {s.generatedCode && (
                  <div>
                    <div className={styles.sectionTitle}>Transpiled Output AST / SQL</div>
                    <pre className={`${styles.codeBox} mono`}>{s.generatedCode}</pre>
                  </div>
                )}

                <div>
                  <div className={styles.sectionTitle}>Real-time Execution Logs</div>
                  <div className={`${styles.logBox} mono`}>
                    {s.logs.map((l, i) => (
                      <div key={i}>{l}</div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
