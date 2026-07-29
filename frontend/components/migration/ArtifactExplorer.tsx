"use client";

import React from "react";
import { FileText, Download, FileCode, Layers, ShieldCheck, Database, FileSpreadsheet } from "lucide-react";
import Button from "@/components/ui/Button";
import styles from "./ArtifactExplorer.module.css";

export interface MigrationArtifact {
  id: string;
  name: string;
  filename: string;
  type: string;
  size: string;
  content: string;
}

interface ArtifactExplorerProps {
  jobUuid?: string;
}

export default function ArtifactExplorer({ jobUuid = "8f93a2b1" }: ArtifactExplorerProps) {
  const artifacts: MigrationArtifact[] = [
    {
      id: "art-1",
      name: "Source Tableau XML",
      filename: `${jobUuid.slice(0, 8)}_source.twb`,
      type: "XML Document",
      size: "42 KB",
      content: `<workbook version='18.1'><datasources><datasource name='Orders'/></datasources></workbook>`,
    },
    {
      id: "art-2",
      name: "Extracted TOM Model",
      filename: `${jobUuid.slice(0, 8)}_tom.json`,
      type: "JSON Model",
      size: "18 KB",
      content: JSON.stringify({ version: "1.0", fields: 42, datasources: ["orders"] }, null, 2),
    },
    {
      id: "art-3",
      name: "Calculated Field DAG",
      filename: `${jobUuid.slice(0, 8)}_dag.json`,
      type: "Dependency Graph",
      size: "12 KB",
      content: JSON.stringify({ nodes: ["Profit_Ratio", "Running_Sales"], edges: 8 }, null, 2),
    },
    {
      id: "art-4",
      name: "Transpiled Spark SQL",
      filename: `${jobUuid.slice(0, 8)}_queries.sql`,
      type: "SQL Script",
      size: "8 KB",
      content: `-- Transpiled Spark SQL for Databricks Lakeview\nSELECT Order_Date, SUM(Sales) FROM orders GROUP BY 1;`,
    },
    {
      id: "art-5",
      name: "Lakeview Dashboard AST",
      filename: `${jobUuid.slice(0, 8)}.lvdash.json`,
      type: "Lakeview AST",
      size: "24 KB",
      content: JSON.stringify({ pages: [{ name: "Overview", widgets: [] }] }, null, 2),
    },
    {
      id: "art-6",
      name: "6-Tier Validation Report",
      filename: `${jobUuid.slice(0, 8)}_validation.json`,
      type: "Validation Report",
      size: "6 KB",
      content: JSON.stringify({ complianceScore: 100, tiersPassed: 6 }, null, 2),
    },
    {
      id: "art-7",
      name: "Databricks Bundle Config",
      filename: "databricks.yml",
      type: "YAML Manifest",
      size: "2 KB",
      content: `bundle:\n  name: migration_${jobUuid.slice(0, 8)}\nresources:\n  dashboards:\n    lakeview:\n      file_path: ./${jobUuid.slice(0, 8)}.lvdash.json`,
    },
  ];

  const handleDownload = (artifact: MigrationArtifact) => {
    const blob = new Blob([artifact.content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = artifact.filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={styles.container}>
      <h3 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
        Migration Artifact Explorer
      </h3>
      <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
        Inspect and download intermediate pipeline artifacts generated during reverse-engineering and compilation.
      </p>

      <div className={styles.grid}>
        {artifacts.map((art) => (
          <div key={art.id} className={styles.artifactCard}>
            <div className={styles.header}>
              <div className={styles.iconBox}>
                {art.filename.endsWith(".sql") ? (
                  <FileCode size={20} />
                ) : art.filename.endsWith(".yml") ? (
                  <Layers size={20} />
                ) : (
                  <FileText size={20} />
                )}
              </div>
              <div>
                <div className={styles.name}>{art.name}</div>
                <div className={`${styles.meta} mono`}>{art.filename}</div>
              </div>
            </div>

            <div className={styles.footer}>
              <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                {art.type} • {art.size}
              </span>
              <Button
                variant="secondary"
                size="sm"
                icon={<Download size={14} />}
                onClick={() => handleDownload(art)}
              >
                Download
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
