"use client";

import React, { useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Download,
  Sparkles,
  Code2,
  Copy,
  Check,
  Search,
  FileCode,
  FileText,
  Filter,
  ShieldCheck,
} from "lucide-react";
import type { StageDetail } from "@/lib/types";
import styles from "./CalcLogicConversionDetail.module.css";

interface CalcLogicConversionDetailProps {
  jobUuid: string;
  stage: StageDetail;
}

export default function CalcLogicConversionDetail({
  jobUuid,
  stage,
}: CalcLogicConversionDetailProps) {
  const artifacts = (stage.artifacts || {}) as Record<string, any>;
  const metrics = (stage.metrics || {}) as Record<string, any>;

  const rawConversions = Array.isArray(artifacts.conversions) ? artifacts.conversions : [];
  const unsupported = Array.isArray(artifacts.unsupported) ? artifacts.unsupported : [];

  const [activeTab, setActiveTab] = useState<"CARDS" | "SQL_SCRIPT" | "UNSUPPORTED">("CARDS");
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [copiedIndex, setCopiedIndex] = useState<string | null>(null);
  const [copiedScript, setCopiedScript] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);

  // Filter conversions list based on search and formula type filter
  const filteredConversions = rawConversions.filter((item: any) => {
    const nameStr = (item.caption || item.name || "").toLowerCase();
    const origStr = (item.original_formula || "").toLowerCase();
    const sqlStr = (item.compiled_sql || "").toLowerCase();
    const q = searchQuery.toLowerCase();

    const matchesSearch = !q || nameStr.includes(q) || origStr.includes(q) || sqlStr.includes(q);
    if (!matchesSearch) return false;

    if (typeFilter === "ALL") return true;
    if (typeFilter === "LOD") return item.formula_type === "LOD" || origStr.includes("fixed") || origStr.includes("include");
    if (typeFilter === "CONDITIONAL") return item.formula_type === "CONDITIONAL" || origStr.includes("if") || origStr.includes("case");
    if (typeFilter === "TABLE_CALC") return item.formula_type === "TABLE_CALC" || origStr.includes("running_") || origStr.includes("rank");
    return true;
  });

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(id);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const handleDownload = async (exportType: string, filename: string) => {
    try {
      setDownloading(exportType);
      const res = await fetch(`/api/v1/migrations/${jobUuid}/exports/${exportType}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch export: ${res.statusText}`);
      }
      const data = await res.json();
      const element = document.createElement("a");
      const file = new Blob([data.content || JSON.stringify(data, null, 2)], {
        type: data.mime_type || "text/plain",
      });
      element.href = URL.createObjectURL(file);
      element.download = data.filename || filename;
      document.body.appendChild(element);
      element.click();
      document.body.removeChild(element);
    } catch (err) {
      console.error("Export download failed:", err);
    } finally {
      setDownloading(null);
    }
  };

  const totalCalculations = metrics.total_expressions ?? rawConversions.length;
  const validCount = metrics.expressions_compiled ?? rawConversions.filter((c: any) => c.validation_status === "VALID").length;
  const reviewCount = metrics.expressions_unsupported ?? unsupported.length;
  const lodCount = rawConversions.filter((c: any) => c.formula_type === "LOD" || (c.original_formula && /FIXED|INCLUDE|EXCLUDE/i.test(c.original_formula))).length;
  const compatScore = metrics.databricks_compatibility ?? (totalCalculations ? Math.round((validCount / totalCalculations) * 100) : 100);

  return (
    <div className={styles.container}>
      {/* ── Metric Header ── */}
      <div className={styles.kpiGrid}>
        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>Calculated Fields</span>
          <span className={styles.kpiValue}>{totalCalculations}</span>
        </div>
        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>Compiled to Databricks SQL</span>
          <span className={styles.kpiValue}>{validCount}</span>
        </div>
        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>LOD & Complex Formulas</span>
          <span className={styles.kpiValue}>{lodCount}</span>
        </div>
        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>Manual Review / Failed</span>
          <span className={styles.kpiValue}>{reviewCount}</span>
        </div>
        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>Databricks SQL Compatibility</span>
          <span className={styles.kpiValue}>{compatScore}%</span>
        </div>
      </div>

      {/* ── Toolbar: Tab Controls & Search/Filter ── */}
      <div className={styles.toolbar}>
        <div className={styles.tabGroup}>
          <button
            className={`${styles.tabBtn} ${activeTab === "CARDS" ? styles.tabBtnActive : ""}`}
            onClick={() => setActiveTab("CARDS")}
          >
            <Code2 size={15} /> Tableau → Databricks SQL Cards
            <span className={styles.badgeCount}>{filteredConversions.length}</span>
          </button>
          <button
            className={`${styles.tabBtn} ${activeTab === "SQL_SCRIPT" ? styles.tabBtnActive : ""}`}
            onClick={() => setActiveTab("SQL_SCRIPT")}
          >
            <FileCode size={15} /> Full Databricks SQL Script (.sql)
          </button>
          {unsupported.length > 0 && (
            <button
              className={`${styles.tabBtn} ${activeTab === "UNSUPPORTED" ? styles.tabBtnActive : ""}`}
              onClick={() => setActiveTab("UNSUPPORTED")}
            >
              <AlertTriangle size={15} /> Manual Review Queue
              <span className={styles.badgeCount}>{unsupported.length}</span>
            </button>
          )}
        </div>

        {activeTab === "CARDS" && (
          <div className={styles.filterControls}>
            <div className={styles.searchBox}>
              <Search size={14} style={{ color: "var(--text-tertiary)" }} />
              <input
                type="text"
                placeholder="Search calculated field or SQL..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className={styles.filterBox}>
              <Filter size={14} style={{ color: "var(--text-tertiary)" }} />
              <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
                <option value="ALL">All Formula Types</option>
                <option value="LOD">LOD Expressions</option>
                <option value="CONDITIONAL">Conditional (IF / CASE)</option>
                <option value="TABLE_CALC">Table Calculations</option>
              </select>
            </div>
          </div>
        )}
      </div>

      {/* ── TAB 1: 1:1 FORMULA TO SQL TRANSLATION CARDS ── */}
      {activeTab === "CARDS" && (
        <div className={styles.cardsList}>
          {filteredConversions.length === 0 ? (
            <div className={styles.emptyState}>No calculated fields match your search filter.</div>
          ) : (
            filteredConversions.map((item: any, idx: number) => {
              const origFormula = (item.original_formula || "").trim();
              const compiledSql = item.compiled_sql || "";
              const status = item.validation_status || "VALID";
              const isFail = status === "FAIL" || /Unable to transpile/i.test(compiledSql);
              const isWarn = status === "WARNING" || (!isFail && (item.is_table_calc || status === "WARNING"));
              const formulaType = item.formula_type || "STANDARD";

              return (
                <div key={idx} className={styles.conversionCard}>
                  {/* Card Header */}
                  <div className={styles.cardHeader}>
                    <div className={styles.cardTitleGroup}>
                      <span className={styles.cardFieldTitle}>{item.caption || item.name}</span>
                      <span className={styles.formulaTypeBadge}>{formulaType}</span>
                      {item.datasource && (
                        <span className={styles.datasourceBadge}>Source: {item.datasource}</span>
                      )}
                    </div>
                    <div>
                      {isFail ? (
                        <span className={styles.statusBadgeWarn}>
                          <AlertTriangle size={13} /> Failed to transpile
                        </span>
                      ) : isWarn ? (
                        <span className={styles.statusBadgeWarn}>
                          <AlertTriangle size={13} /> Requires Review
                        </span>
                      ) : (
                        <span className={styles.statusBadgeValid}>
                          <ShieldCheck size={13} /> Valid Spark SQL
                        </span>
                      )}
                    </div>
                  </div>

                  {/* 1:1 Side-by-Side Code Translation Grid */}
                  <div className={styles.sideBySideGrid}>
                    {/* LEFT PANEL: TABLEAU CALCULATED FIELD FORMULA */}
                    <div className={styles.codeColumn}>
                      <div className={styles.codeColumnHeader}>
                        <span className={styles.codeColumnTitleTableau}>
                          <FileText size={13} /> Tableau Calculated Field / Formula
                        </span>
                        <button
                          className={styles.copyBtn}
                          onClick={() => copyToClipboard(origFormula || item.name || "", `orig-${idx}`)}
                          disabled={!origFormula}
                        >
                          {copiedIndex === `orig-${idx}` ? (
                            <>
                              <Check size={12} style={{ color: "var(--accent-green)" }} /> Copied
                            </>
                          ) : (
                            <>
                              <Copy size={12} /> Copy Formula
                            </>
                          )}
                        </button>
                      </div>
                      <pre className={styles.codeBlock}>
                        <code>{origFormula || "/* No Tableau formula on this field */"}</code>
                      </pre>
                    </div>

                    {/* CENTER DIVIDER */}
                    <div className={styles.centerArrowDivider}>
                      <ArrowRight size={18} />
                      <span className={styles.arrowLabel}>Converted To</span>
                    </div>

                    {/* RIGHT PANEL: CONVERTED DATABRICKS SPARK SQL */}
                    <div className={styles.codeColumn}>
                      <div className={styles.codeColumnHeader}>
                        <span className={styles.codeColumnTitleDatabricks}>
                          <Code2 size={13} /> Databricks Spark SQL Conversion
                        </span>
                        <button
                          className={styles.copyBtn}
                          onClick={() => copyToClipboard(compiledSql, `sql-${idx}`)}
                        >
                          {copiedIndex === `sql-${idx}` ? (
                            <>
                              <Check size={12} style={{ color: "var(--accent-green)" }} /> Copied
                            </>
                          ) : (
                            <>
                              <Copy size={12} /> Copy SQL
                            </>
                          )}
                        </button>
                      </div>
                      <pre className={`${styles.codeBlock} ${styles.codeBlockSql}`}>
                        <code>{compiledSql || "/* No SQL generated */"}</code>
                      </pre>
                    </div>
                  </div>

                  {/* Translation Explanation Callout */}
                  {item.ai_explanation && (
                    <div className={styles.explanationFooter}>
                      <Sparkles size={14} className={styles.sparkleIcon} />
                      <span>
                        <strong>SQL Translation Note: </strong>
                        {item.ai_explanation}
                      </span>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {/* ── TAB 2: FULL DATABRICKS SQL SCRIPT ── */}
      {activeTab === "SQL_SCRIPT" && (
        <div className={styles.fullSqlCard}>
          <div className={styles.fullSqlHeader}>
            <span className={styles.fullSqlTitle}>
              <FileCode size={16} style={{ color: "var(--accent-cyan)" }} /> Transpiled Databricks Spark SQL Script (.sql)
            </span>
            <div className={styles.actionBtnGroup}>
              <button
                className={styles.actionBtn}
                onClick={() => {
                  const sqlText = stage.generated_code || "-- No SQL generated";
                  navigator.clipboard.writeText(sqlText);
                  setCopiedScript(true);
                  setTimeout(() => setCopiedScript(false), 2000);
                }}
              >
                {copiedScript ? <Check size={13} style={{ color: "var(--accent-green)" }} /> : <Copy size={13} />}
                {copiedScript ? "Copied Script" : "Copy Full SQL"}
              </button>

              <button
                className={styles.actionBtn}
                onClick={() => handleDownload("sql", "converted_calculations.sql")}
                disabled={downloading !== null}
              >
                <Download size={13} /> Download .sql File
              </button>
            </div>
          </div>
          <pre className={styles.fullSqlCodeBlock}>
            <code>{stage.generated_code || "-- Transpiled Databricks Spark SQL Script\n-- Extracting calculated fields..."}</code>
          </pre>
        </div>
      )}

      {/* ── TAB 3: MANUAL REVIEW QUEUE ── */}
      {activeTab === "UNSUPPORTED" && (
        <div className={styles.reviewQueueList}>
          {unsupported.map((item: any, idx: number) => (
            <div key={idx} className={styles.reviewCard}>
              <div className={styles.reviewHeader}>
                <span className={styles.reviewTitle}>{item.name || item.caption || "Complex Calculation"}</span>
                <span className={styles.reviewBadge}>Manual SME Review Required</span>
              </div>
              <div className={styles.reviewGrid}>
                <div>
                  <span className={styles.reviewLabel}>Tableau Formula</span>
                  <pre className={styles.codeBlockSmall}>
                    <code>{item.formula || item.original_formula || item.name}</code>
                  </pre>
                </div>
                <div>
                  <span className={styles.reviewLabel}>Limitation & Recommendation</span>
                  <div className={styles.reviewReasonText}>
                    <strong>Reason:</strong> {item.reason || "Uses Tableau-specific table calculation function"}
                  </div>
                  <div className={styles.reviewRecText}>
                    <strong>Suggested Fix:</strong> {item.recommendation || "Replace with Databricks SQL window function or Lakeview calculated field."}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Footer Export Package Bar ── */}
      <div className={styles.exportCard}>
        <span className={styles.exportTitle}>Download Export Package</span>
        <div className={styles.exportBtnGroup}>
          <button
            className={styles.exportBtn}
            onClick={() => handleDownload("calculation-mapping", "calculation_mapping.csv")}
            disabled={downloading !== null}
          >
            <FileText size={14} /> Business Mapping (.csv)
          </button>
          <button
            className={styles.exportBtn}
            onClick={() => handleDownload("sql", "converted_calculations.sql")}
            disabled={downloading !== null}
          >
            <FileCode size={14} /> Transpiled SQL (.sql)
          </button>
          <button
            className={styles.exportBtn}
            onClick={() => handleDownload("compatibility-report", "compatibility_report.json")}
            disabled={downloading !== null}
          >
            <Code2 size={14} /> Compatibility Specs (.json)
          </button>
          <button
            className={styles.exportBtn}
            onClick={() => handleDownload("manual-review-items", "manual_review_queue.csv")}
            disabled={downloading !== null}
          >
            <FileText size={14} /> Manual Review Items (.csv)
          </button>
        </div>
      </div>
    </div>
  );
}
