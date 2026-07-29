"use client";

import { useState } from "react";
import { ArrowRight, CheckCircle2, Copy, Download, Check } from "lucide-react";
import Button from "@/components/ui/Button";
import styles from "./SqlDiffViewer.module.css";

interface SqlDiffViewerProps {
  sourceSql: string;
  targetSql: string;
  datasetName: string;
}

export default function SqlDiffViewer({
  sourceSql,
  targetSql,
  datasetName,
}: SqlDiffViewerProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(targetSql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([targetSql], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${datasetName.toLowerCase().replace(/\s+/g, "_")}_databricks.sql`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={styles.container}>
      <div className={styles.header} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span>SQL Translation: {datasetName}</span>
          <span style={{ color: "var(--accent-green)", fontSize: "var(--font-size-xs)", display: "inline-flex", alignItems: "center", gap: "4px" }}>
            <CheckCircle2 size={14} /> sqlglot Transpiled
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Button variant="ghost" size="sm" icon={copied ? <Check size={12} color="var(--accent-green)" /> : <Copy size={12} />} onClick={handleCopy}>
            {copied ? "Copied!" : "Copy Spark SQL"}
          </Button>
          <Button variant="secondary" size="sm" icon={<Download size={12} />} onClick={handleDownload}>
            Download .sql
          </Button>
        </div>
      </div>

      <div className={styles.grid}>
        <div className={styles.pane}>
          <div className={styles.paneTitle}>Tableau Source SQL</div>
          <pre className={styles.codeBox}>{sourceSql || "-- Raw datasource query"}</pre>
        </div>

        <div className={styles.pane}>
          <div className={styles.paneTitle}>Databricks Spark SQL Target</div>
          <pre className={styles.codeBox}>{targetSql || "-- Transpiled Spark SQL"}</pre>
        </div>
      </div>
    </div>
  );
}
