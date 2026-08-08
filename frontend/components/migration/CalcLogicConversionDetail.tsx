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
import { getLakeviewJson, getStageDetail } from "@/lib/api";
import {
  LakeviewDashboardAdapter,
  buildCalcLabelMap,
  normalizeName,
  resolveCalcLabel,
  type MatchedPair,
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

  const [goldenLoading, setGoldenLoading] = useState(false);
  const [matchedPairs, setMatchedPairs] = useState<MatchedPair[]>([]);
  const [selectedWorksheet, setSelectedWorksheet] = useState<string | null>(null);
  const [parseCalcs, setParseCalcs] = useState<Array<Record<string, unknown>>>([]);
  const [adapter, setAdapter] = useState<LakeviewDashboardAdapter | null>(null);

  useEffect(() => {
    if (!goldenOverride) {
      setMatchedPairs([]);
      setSelectedWorksheet(null);
      setAdapter(null);
      return;
    }

    let cancelled = false;
    setGoldenLoading(true);

    (async () => {
      try {
        const [json, parseStage] = await Promise.all([
          getLakeviewJson(jobUuid),
          getStageDetail(jobUuid, "PARSE").catch(() => null),
        ]);
        if (cancelled) return;

        const parseArtifacts = (parseStage?.artifacts || {}) as Record<string, any>;
        const calcs = Array.isArray(parseArtifacts.calculated_fields)
          ? parseArtifacts.calculated_fields
          : [];
        setParseCalcs(calcs);

        const lv = new LakeviewDashboardAdapter(json);
        setAdapter(lv);

        const names: string[] = [];
        const seen = new Set<string>();
        for (const item of rawConversions) {
          // conversions don't have worksheet — use PARSE detailed_visuals / worksheets
        }
        const detailed = Array.isArray(parseArtifacts.detailed_visuals)
          ? parseArtifacts.detailed_visuals
          : [];
        for (const v of detailed) {
          const n = v?.name || v?.worksheet_name || v?.title;
          if (typeof n === "string" && n && !seen.has(n)) {
            seen.add(n);
            names.push(n);
          }
        }
        const wsList = Array.isArray(parseArtifacts.worksheets) ? parseArtifacts.worksheets : [];
        for (const w of wsList) {
          const n = typeof w === "string" ? w : w?.name;
          if (typeof n === "string" && n && !seen.has(n)) {
            seen.add(n);
            names.push(n);
          }
        }
        // Fallback: match conversion captions against widget titles if no PARSE names
        if (names.length === 0) {
          for (const w of lv.getChartWidgets()) {
            if (w.title && !seen.has(w.title)) {
              seen.add(w.title);
              names.push(w.title);
            }
          }
        }

        const pairs = lv.matchWorksheets(names);
        setMatchedPairs(pairs);
        setSelectedWorksheet(pairs[0]?.tableauWorksheetName ?? null);
      } catch {
        if (!cancelled) {
          setMatchedPairs([]);
          setSelectedWorksheet(null);
        }
      } finally {
        if (!cancelled) setGoldenLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [goldenOverride, jobUuid, stage.artifacts]);

  const calcLabelMap = useMemo(
    () => buildCalcLabelMap(rawConversions, parseCalcs),
    [rawConversions, parseCalcs]
  );

  const selectedPair = useMemo(
    () => matchedPairs.find((p) => p.tableauWorksheetName === selectedWorksheet) || null,
    [matchedPairs, selectedWorksheet]
  );

  const selectedFieldKeys = useMemo(() => {
    if (!adapter || !selectedPair) return new Set<string>();
    return adapter.getNormalizedFieldKeys(selectedPair.widget);
  }, [adapter, selectedPair]);

  /** Filter conversions: search/type always; golden mode also requires field linkage. */
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

    if (goldenOverride && selectedWorksheet) {
      // Must link to selected golden widget field set
      const candidates = [
        item.caption,
        item.name,
        item.internal_name,
        ...(typeof item.name === "string" ? [item.name] : []),
      ].filter(Boolean) as string[];

      const linked = candidates.some((c) => {
        const n = normalizeName(c);
        if (n && selectedFieldKeys.has(n)) return true;
        // raw Calculation_ id in field keys
        if (selectedFieldKeys.has(c)) return true;
        const label = resolveCalcLabel(c, calcLabelMap);
        if (normalizeName(label) && selectedFieldKeys.has(normalizeName(label))) return true;
        return false;
      });
      return linked;
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

  const usageFor = (item: any) => {
    if (!selectedPair || !adapter) return null;
    const fields = adapter.getFieldNames(selectedPair.widget);
    const label = displayNameFor(item);
    const matchedField =
      fields.find((f) => normalizeName(f) === normalizeName(label)) ||
      fields.find((f) => normalizeName(f) === normalizeName(item.name)) ||
      fields.find((f) => normalizeName(f) === normalizeName(item.caption)) ||
      null;
    return {
      usedBy: selectedPair.tableauWorksheetName,
      widgetTitle: selectedPair.widget.title,
      field: matchedField || label,
      sourceFields: adapter.getDimensions(selectedPair.widget).concat(adapter.getMeasures(selectedPair.widget)),
    };
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
        <div className={goldenOverride ? styles.goldenLayout : undefined}>
          {goldenOverride && (
            <div className={styles.goldenRail}>
              <div className={styles.goldenRailTitle}>Worksheets</div>
              {goldenLoading && <div className={styles.emptyState}>Loading…</div>}
              {!goldenLoading && matchedPairs.length === 0 && (
                <div className={styles.emptyState}>
                  No matched visuals between Tableau worksheets and curated Lakeview widgets
                </div>
              )}
              {matchedPairs.map((p) => (
                <button
                  key={p.tableauWorksheetName}
                  type="button"
                  className={`${styles.goldenRailItem} ${
                    selectedWorksheet === p.tableauWorksheetName ? styles.goldenRailItemActive : ""
                  }`}
                  onClick={() => setSelectedWorksheet(p.tableauWorksheetName)}
                >
                  {p.tableauWorksheetName}
                </button>
              ))}
            </div>
          )}

          <div className={styles.cardsList}>
            {goldenOverride && selectedWorksheet && filteredConversions.length === 0 && !goldenLoading ? (
              <div className={styles.emptyState}>
                No linked calculations found for this worksheet.
              </div>
            ) : filteredConversions.length === 0 ? (
              <div className={styles.emptyState}>No calculated fields match your search filter.</div>
            ) : (
              filteredConversions.map((item: any, idx: number) => {
                const origFormula = (item.original_formula || "").trim();
                const compiledSql = item.compiled_sql || "";
                const status = item.validation_status || "VALID";
                const isFail = status === "FAIL" || /Unable to transpile/i.test(compiledSql);
                const isWarn =
                  status === "WARNING" || (!isFail && (item.is_table_calc || status === "WARNING"));
                const formulaType = item.formula_type || "STANDARD";
                const title = displayNameFor(item);
                const usage = goldenOverride ? usageFor(item) : null;

                return (
                  <div key={idx} className={styles.conversionCard}>
                    <div className={styles.cardHeader}>
                      <div className={styles.cardTitleGroup}>
                        <span className={styles.cardFieldTitle}>{title}</span>
                        <span className={styles.formulaTypeBadge}>{formulaType}</span>
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
                        ) : (
                          <span className={styles.statusBadgeValid}>
                            <ShieldCheck size={13} /> Valid Spark SQL
                          </span>
                        )}
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
                        {compiledSql && (
                          <pre className={`${styles.codeBlock} ${styles.codeBlockSql}`} style={{ marginTop: "0.5rem" }}>
                            <code>{compiledSql}</code>
                          </pre>
                        )}
                      </div>

                      <div className={styles.centerArrowDivider}>
                        <ArrowRight size={18} />
                        <span className={styles.arrowLabel}>
                          {goldenOverride ? "Used In" : "Converted To"}
                        </span>
                      </div>

                      <div className={styles.codeColumn}>
                        <div className={styles.codeColumnHeader}>
                          <span className={styles.codeColumnTitleDatabricks}>
                            <Code2 size={13} />{" "}
                            {goldenOverride
                              ? "Lakeview Visual Usage"
                              : "Databricks Spark SQL Conversion"}
                          </span>
                          {!goldenOverride && (
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
                          )}
                        </div>
                        {goldenOverride && usage ? (
                          <div className={styles.usagePanel}>
                            <div>
                              <div className={styles.usageLabel}>Calculated Field</div>
                              <div className={styles.usageValue}>{title}</div>
                            </div>
                            <div>
                              <div className={styles.usageLabel}>Used By</div>
                              <div className={styles.usageValue}>{usage.usedBy}</div>
                            </div>
                            <div>
                              <div className={styles.usageLabel}>Lakeview Widget</div>
                              <div className={styles.usageValue}>{usage.widgetTitle}</div>
                            </div>
                            <div>
                              <div className={styles.usageLabel}>Field in Visual</div>
                              <div className={styles.usageValue}>{usage.field}</div>
                            </div>
                            {usage.sourceFields.length > 0 && (
                              <div>
                                <div className={styles.usageLabel}>Source Fields</div>
                                <div className={styles.usageValue}>{usage.sourceFields.join(", ")}</div>
                              </div>
                            )}
                          </div>
                        ) : (
                          <pre className={`${styles.codeBlock} ${styles.codeBlockSql}`}>
                            <code>{compiledSql || "/* No SQL generated */"}</code>
                          </pre>
                        )}
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
