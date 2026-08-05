"use client";

import React from "react";
import { ArrowRight, Sparkles, CheckCircle2, AlertTriangle, Code2 } from "lucide-react";
import type { FormulaConversionItem } from "@/lib/types";
import styles from "./FormulaConversionCard.module.css";

interface FormulaConversionCardProps {
  item: FormulaConversionItem;
}

export default function FormulaConversionCard({ item }: FormulaConversionCardProps) {
  const isFail = item.validation_status === "FAIL" || /Unable to transpile/i.test(item.compiled_sql || "");
  const isWarning =
    !isFail &&
    (item.validation_status === "WARNING" ||
      item.is_table_calc ||
      (item.confidence_score !== undefined && item.confidence_score < 80));
  const formula = (item.original_formula || "").trim();

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div className={styles.fieldName}>
          <Code2 size={16} style={{ color: "var(--accent-cyan)" }} />
          {item.caption || item.name}
        </div>
        <div className={styles.metaRow}>
          {item.formula_type && (
            <span className={styles.confidenceBadge}>{item.formula_type}</span>
          )}
          {item.confidence_score !== undefined && (
            <span className={styles.confidenceBadge}>{item.confidence_score}% Confidence</span>
          )}
          <span className={isFail || isWarning ? styles.statusBadgeWarn : styles.statusBadgeValid}>
            {isFail ? (
              <>
                <AlertTriangle size={11} style={{ display: "inline", marginRight: 4 }} />
                Failed
              </>
            ) : isWarning ? (
              <>
                <AlertTriangle size={11} style={{ display: "inline", marginRight: 4 }} />
                Requires Review
              </>
            ) : (
              <>
                <CheckCircle2 size={11} style={{ display: "inline", marginRight: 4 }} />
                Compatible
              </>
            )}
          </span>
        </div>
      </div>

      <div className={styles.conversionGrid}>
        {/* Left: Original Tableau Formula */}
        <div className={styles.box}>
          <div className={styles.boxLabel}>Original Tableau Formula</div>
          <code>{formula || "/* No Tableau formula */"}</code>
        </div>

        {/* Center: Conversion Arrow */}
        <div className={styles.arrowIcon}>
          <ArrowRight size={18} />
        </div>

        {/* Right: Converted Databricks SQL */}
        <div className={styles.box} style={{ borderColor: "rgba(0, 168, 204, 0.3)" }}>
          <div className={styles.boxLabel} style={{ color: "var(--accent-cyan)" }}>
            Generated Databricks SQL
          </div>
          <code>{item.compiled_sql}</code>
        </div>
      </div>

      {/* AI Explanation Bar */}
      {item.ai_explanation && (
        <div className={styles.aiSection}>
          <Sparkles size={15} className={styles.aiIcon} />
          <div>
            <strong style={{ color: "var(--text-primary)" }}>AI Conversion Note: </strong>
            {item.ai_explanation}
          </div>
        </div>
      )}
    </div>
  );
}
