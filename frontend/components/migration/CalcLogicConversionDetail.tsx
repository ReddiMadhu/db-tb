"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
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
import { getLakeviewJson, getStageDetail, getMigrationStatus } from "@/lib/api";
import {
  buildCalcLabelMap,
  buildSemanticExprIndex,
  resolveCalcLabel,
  resolveSemanticExpr,
} from "@/lib/lakeviewDashboardAdapter";
import styles from "./CalcLogicConversionDetail.module.css";

interface CalcLogicConversionDetailProps {
  jobUuid: string;
  stage: StageDetail;
  goldenOverride?: boolean;
}

export default function CalcLogicConversionDetail({
  jobUuid,
  stage,
  goldenOverride = false,
}: CalcLogicConversionDetailProps) {
  const artifacts = (stage.artifacts || {}) as Record<string, any>;
  const metrics = (stage.metrics || {}) as Record<string, any>;

  const rawConversions = Array.isArray(artifacts.conversions) ? artifacts.conversions : [];

  const [activeTab, setActiveTab] = useState<"CARDS" | "SQL_SCRIPT" | "UNSUPPORTED">("CARDS");
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [copiedIndex, setCopiedIndex] = useState<string | null>(null);
  const [copiedScript, setCopiedScript] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);

  const [parseCalcs, setParseCalcs] = useState<Array<Record<string, unknown>>>([]);
  const [goldenExprIndex, setGoldenExprIndex] = useState<Map<string, string>>(() => new Map());
  const [resolvedGolden, setResolvedGolden] = useState(Boolean(goldenOverride));

  useEffect(() => {
    if (goldenOverride) {
      setResolvedGolden(true);
      return;
    }
    let cancelled = false;
    getMigrationStatus(jobUuid)
      .then((s) => {
        if (!cancelled) setResolvedGolden(Boolean(s.golden_override));
      })
      .catch(() => {
        if (!cancelled) setResolvedGolden(false);
      });
    return () => {
      cancelled = true;
    };
  }, [goldenOverride, jobUuid]);

  const isGolden = resolvedGolden;

  useEffect(() => {
    if (!isGolden) {
      setGoldenExprIndex(new Map());
      setParseCalcs([]);
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const [json, parseStage, layoutStage] = await Promise.all([
          getLakeviewJson(jobUuid),
          getStageDetail(jobUuid, "PARSE").catch(() => null),
          getStageDetail(jobUuid, "LAYOUT_GENERATION").catch(() => null),
        ]);
        if (cancelled) return;

        let dashboardJson: unknown = json;
        const layoutArts = (layoutStage?.artifacts || {}) as Record<string, any>;
        if (typeof layoutArts.lakeview_json_str === "string" && layoutArts.lakeview_json_str.trim().startsWith("{")) {
          try {
            dashboardJson = JSON.parse(layoutArts.lakeview_json_str);
          } catch {
            /* keep /json */
          }
        }

        const parseArtifacts = (parseStage?.artifacts || {}) as Record<string, any>;
        const calcs = Array.isArray(parseArtifacts.calculated_fields)
          ? parseArtifacts.calculated_fields
          : [];
        setParseCalcs(calcs);
        setGoldenExprIndex(buildSemanticExprIndex(dashboardJson));
      } catch {
        if (!cancelled) {
          setGoldenExprIndex(new Map());
          setParseCalcs([]);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isGolden, jobUuid, stage.artifacts]);

  const calcLabelMap = useMemo(
    () => buildCalcLabelMap(rawConversions, parseCalcs),
    [rawConversions, parseCalcs]
  );

  /** Filter conversions: search + type only (all calcs, golden or not). */
  const filteredConversions = rawConversions.filter((item: any) => {
    const caption = item.caption || item.name || "";
    const nameStr = caption.toLowerCase();
    const origStr = (item.original_formula || "").toLowerCase();
    const sqlStr = (item.compiled_sql || "").toLowerCase();
    const q = searchQuery.toLowerCase();

    const matchesSearch = !q || nameStr.includes(q) || origStr.includes(q) || sqlStr.includes(q);
    if (!matchesSearch) return false;

    if (typeFilter === "LOD") {
      if (!(item.formula_type === "LOD" || origStr.includes("fixed") || origStr.includes("include"))) {
        return false;
      }
    } else if (typeFilter === "CONDITIONAL") {
      if (!(item.formula_type === "CONDITIONAL" || origStr.includes("if") || origStr.includes("case"))) {
        return false;
      }
    } else if (typeFilter === "TABLE_CALC") {
      if (
        !(
          item.formula_type === "TABLE_CALC" ||
          origStr.includes("running_") ||
          origStr.includes("rank")
        )
      ) {
        return false;
      }
    }

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
  const validCount =
    metrics.expressions_compiled ??
    rawConversions.filter((c: any) => c.validation_status === "VALID").length;

  const displayNameFor = (item: any) => {
    const raw = item.caption || item.name || "";
    return resolveCalcLabel(raw, calcLabelMap);
  };

  const databricksSqlFor = (item: any): { sql: string; fromGolden: boolean } => {
    if (isGolden && goldenExprIndex.size > 0) {
      const golden = resolveSemanticExpr(item, goldenExprIndex, calcLabelMap);
      if (golden) return { sql: golden, fromGolden: true };
    }
    const compiled = typeof item.compiled_sql === "string" ? item.compiled_sql.trim() : "";
    if (compiled) return { sql: compiled, fromGolden: false };
    return { sql: "/* No Databricks SQL for this calculation */", fromGolden: false };
  };

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

      {/* ── TAB 1: FORMULA CARDS ── */}
      {activeTab === "CARDS" && (
        <div className={styles.cardsList}>
          {filteredConversions.length === 0 ? (
            <div className={styles.emptyState}>No calculated fields match your search filter.</div>
          ) : (
            filteredConversions.map((item: any, idx: number) => {
              const origFormula = (item.original_formula || "").trim();
              const { sql: displaySql, fromGolden } = databricksSqlFor(item);
              const compiledSql = typeof item.compiled_sql === "string" ? item.compiled_sql : "";
              const status = item.validation_status || "VALID";
              const isFail = status === "FAIL" || /Unable to transpile/i.test(compiledSql);
              const isWarn =
                status === "WARNING" || (!isFail && (item.is_table_calc || status === "WARNING"));
              const formulaType = item.formula_type || "STANDARD";
              const title = displayNameFor(item);

              return (
                <div key={idx} className={styles.conversionCard}>
                  <div className={styles.cardHeader}>
                    <div className={styles.cardTitleGroup}>
                      <span className={styles.cardFieldTitle}>{title}</span>
                      <span className={styles.formulaTypeBadge}>{formulaType}</span>
                      {fromGolden && (
                        <span className={styles.goldenSqlBadge} title="SQL from golden Lakeview semantic model">
                          <ShieldCheck size={12} /> Golden
                        </span>
                      )}
                      {item.datasource && (
                        <span className={styles.datasourceBadge}>
                          Source:{" "}
                          {item.datasource.startsWith("federated.")
                            ? "Datasource"
                            : item.datasource}
                        </span>
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
                      ) : null}
                    </div>
                  </div>

                  <div className={styles.sideBySideGrid}>
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

                    <div className={styles.centerArrowDivider}>
                      <ArrowRight size={18} />
                      <span className={styles.arrowLabel}>Converted To</span>
                    </div>

                    <div className={styles.codeColumn}>
                      <div className={styles.codeColumnHeader}>
                        <span className={styles.codeColumnTitleDatabricks}>
                          <Code2 size={13} /> Databricks Spark SQL Conversion
                        </span>
                        <button
                          className={styles.copyBtn}
                          onClick={() => copyToClipboard(displaySql, `sql-${idx}`)}
                          disabled={!displaySql || displaySql.startsWith("/* No Databricks")}
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
                        <code>{displaySql}</code>
                      </pre>
                    </div>
                  </div>

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
              <FileCode size={16} style={{ color: "var(--accent-cyan)" }} /> Transpiled Databricks Spark
              SQL Script (.sql)
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
                {copiedScript ? (
                  <Check size={13} style={{ color: "var(--accent-green)" }} />
                ) : (
                  <Copy size={13} />
                )}
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
            <code>
              {stage.generated_code ||
                "-- Transpiled Databricks Spark SQL Script\n-- Extracting calculated fields..."}
            </code>
          </pre>
        </div>
      )}
    </div>
  );
}
