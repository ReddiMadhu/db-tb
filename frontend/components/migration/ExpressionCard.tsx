"use client";

import { useState } from "react";
import { Sparkles, CheckCircle2 } from "lucide-react";
import Button from "@/components/ui/Button";
import ExpressionExplainModal from "./ExpressionExplainModal";
import styles from "./ExpressionCard.module.css";

interface ExpressionCardProps {
  name: string;
  type: string; // STANDARD, LOD, TABLE_CALC
  sourceFormula: string;
  targetSql: string;
  confidence?: number;
  method?: string;
}

export default function ExpressionCard({
  name,
  type,
  sourceFormula,
  targetSql,
  confidence = 98,
  method = "Rule-based Engine",
}: ExpressionCardProps) {
  const [explainOpen, setExplainOpen] = useState(false);

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <span className={styles.name}>{name}</span>
          <span className={styles.typeBadge}>{type}</span>
        </div>

        <div className={styles.confidenceMeter}>
          <span>Confidence {confidence}%</span>
          <div className={styles.meterBar}>
            <div className={styles.meterFill} style={{ width: `${confidence}%` }} />
          </div>
        </div>
      </div>

      <div className={styles.formulaBox}>
        <div>
          <div className={styles.boxLabel}>Tableau Formula</div>
          <div className={styles.box}>{sourceFormula}</div>
        </div>

        <div>
          <div className={styles.boxLabel}>Databricks Spark SQL</div>
          <div className={styles.box} style={{ color: "var(--accent-green)" }}>
            {targetSql}
          </div>
        </div>
      </div>

      <div className={styles.footer}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
          Method: {method} <CheckCircle2 size={12} color="var(--accent-green)" />
        </span>
        <Button variant="ghost" size="sm" icon={<Sparkles size={12} />} onClick={() => setExplainOpen(true)}>
          AI Explain
        </Button>
      </div>

      {explainOpen && (
        <ExpressionExplainModal
          isOpen={explainOpen}
          name={name}
          type={type}
          sourceFormula={sourceFormula}
          targetSql={targetSql}
          confidence={confidence}
          method={method}
          onClose={() => setExplainOpen(false)}
        />
      )}
    </div>
  );
}
