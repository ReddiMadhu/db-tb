"use client";

import React, { useState, useMemo, useCallback } from "react";
import {
  BarChart3,
  TrendingUp,
  Calculator,
  Database,
  Search,
  ChevronRight,
  Filter,
  Layers,
  PieChart,
  LineChart,
  Table as TableIcon,
  Activity,
  LayoutDashboard,
} from "lucide-react";
import type { StageDetail } from "@/lib/types";
import styles from "./ParseStageDetail.module.css";

/* ═══════════════════════════════════════
   Types
   ═══════════════════════════════════════ */
interface WorksheetVisual {
  name: string;
  title: string;
  type: string;
  mark_type: string;
  worksheet: string;
  columns: string[];
  rows: string[];
  measures: string[];
  dimensions: string[];
  filters: string[];
  encoding: string;
  tooltip: string;
  datasource_name?: string;
  used_calculated_fields?: string[];
  rows_shelves?: { field_name: string; derivation: string | null; raw: string }[];
  columns_shelves?: { field_name: string; derivation: string | null; raw: string }[];
  encodings?: { channel: string; field_name: string; field_type: string; aggregation: string | null; derivation: string | null }[];
  sorts?: { field_name: string; direction: string; sort_type: string }[];
  filter_details?: { field_name: string; filter_type: string; is_context_filter: boolean; is_global: boolean; scope: string }[];
}

interface CalcField {
  name: string;
  caption: string;
  formula: string;
  type: string;
  datasource: string;
}

interface ParseStageDetailProps {
  jobUuid: string;
  stage: StageDetail;
  onSelectNextStage?: (stageId: string) => void;
}

/* ═══════════════════════════════════════
   Helpers
   ═══════════════════════════════════════ */
function getChartIcon(type: string) {
  const t = type.toLowerCase();
  if (/bar/i.test(t)) return BarChart3;
  if (/line|area|trend/i.test(t)) return LineChart;
  if (/pie|donut/i.test(t)) return PieChart;
  if (/scatter|bubble/i.test(t)) return Activity;
  if (/table|grid|matrix|highlight|text|crosstab/i.test(t)) return TableIcon;
  if (/map|geo/i.test(t)) return LayoutDashboard;
  return BarChart3;
}

function getChartColor(type: string): string {
  const t = type.toLowerCase();
  if (/bar/i.test(t)) return "#00A8CC";
  if (/line|area|trend/i.test(t)) return "#F2994A";
  if (/pie|donut/i.test(t)) return "#27AE60";
  if (/scatter|bubble/i.test(t)) return "#9B51E0";
  if (/table|grid|matrix|highlight|text|crosstab/i.test(t)) return "#E2B93B";
  if (/map|geo/i.test(t)) return "#2D9CDB";
  return "#00A8CC";
}

function getCompatibility(ws: WorksheetVisual): { label: string; cls: string } {
  const t = ws.type.toLowerCase();
  if (/map|geo|gantt|waterfall/i.test(t)) return { label: "Needs Review", cls: styles.compatAmber };
  if (/box|violin|treemap/i.test(t)) return { label: "Limited", cls: styles.compatRed };
  return { label: "Compatible", cls: styles.compatGreen };
}

function calcComplexity(formula: string): string {
  if (!formula) return "Low";
  const upper = formula.toUpperCase();
  if (/FIXED|INCLUDE|EXCLUDE/i.test(upper)) return "High";
  if (/WINDOW_|RUNNING_|LOOKUP|INDEX|FIRST|LAST|RAWSQL/i.test(upper)) return "High";
  if (/IF|CASE|IIF|ZN|IFNULL/i.test(upper)) return "Medium";
  return "Low";
}

/* ═══════════════════════════════════════
   COMPONENT
   ═══════════════════════════════════════ */
export default function ParseStageDetail({ jobUuid, stage }: ParseStageDetailProps) {
  // ── State ──
  const [selectedWs, setSelectedWs] = useState<string | null>(null);
  const [selectedCalc, setSelectedCalc] = useState<string | null>(null);
  const [selectedTable, setSelectedTable] = useState<string>("");
  const [wsSearch, setWsSearch] = useState("");
  const [calcSearch, setCalcSearch] = useState("");
  const [expandedWs, setExpandedWs] = useState<Set<string>>(new Set());
  const [expandedCalcs, setExpandedCalcs] = useState<Set<string>>(new Set());

  const artifacts = (stage.artifacts || {}) as Record<string, any>;
  const metrics = (stage.metrics || {}) as Record<string, any>;

  // ── Extract Data ──
  const worksheets: WorksheetVisual[] = useMemo(() => {
    if (Array.isArray(artifacts.detailed_visuals) && artifacts.detailed_visuals.length > 0) {
      return artifacts.detailed_visuals;
    }
    const wsList: string[] = Array.isArray(artifacts.worksheets)
      ? artifacts.worksheets.map((w: any) => (typeof w === "string" ? w : w.name || "Worksheet"))
      : [];
    return wsList.map((name, idx) => ({
      name,
      title: name,
      type: idx % 3 === 0 ? "Bar Chart" : idx % 3 === 1 ? "Line Chart" : "Table",
      mark_type: "Automatic",
      worksheet: name,
      columns: [],
      rows: [],
      measures: (artifacts.measures || []).slice(0, 2),
      dimensions: (artifacts.dimensions || []).slice(0, 2),
      filters: [],
      encoding: "",
      tooltip: "",
    }));
  }, [artifacts]);

  const calcFields: CalcField[] = useMemo(() => {
    if (!Array.isArray(artifacts.calculated_fields)) return [];
    return artifacts.calculated_fields.map((cf: any) => ({
      name: cf.name || "",
      caption: cf.caption || cf.name || "Calculation",
      formula: cf.formula || "",
      type: cf.type || cf.formula_type || "STANDARD",
      datasource: cf.datasource || "Default",
    }));
  }, [artifacts]);

  const measuresList: string[] = Array.isArray(artifacts.measures) ? artifacts.measures : [];
  const joins = Array.isArray(artifacts.joins) ? artifacts.joins : [];
  const relationships = Array.isArray(artifacts.relationships) ? artifacts.relationships : [];
  const datasources = Array.isArray(artifacts.datasources) ? artifacts.datasources : [];

  const dashboardName = artifacts.dashboard_name || artifacts.dashboard_title || "Workbook Dashboard";

  // ── Counts ──
  const dashboardCount = metrics.dashboards_parsed ?? (artifacts.dashboards ? artifacts.dashboards.length : 0);
  const wsCount = worksheets.length;
  const calcCount = calcFields.length;
  const dsCount = metrics.datasource_count ?? datasources.length;

  // ── Selected Worksheet ──
  const selectedVisual = useMemo(
    () => worksheets.find((w) => w.name === selectedWs) || null,
    [worksheets, selectedWs]
  );

  // ── Build reverse lookup: calc field name → worksheet names ──
  const calcToWorksheets = useMemo(() => {
    const map = new Map<string, string[]>();
    worksheets.forEach((ws) => {
      const usedCalcs = ws.used_calculated_fields || [];
      usedCalcs.forEach((cfName) => {
        if (!map.has(cfName)) map.set(cfName, []);
        map.get(cfName)!.push(ws.name);
      });
    });
    return map;
  }, [worksheets]);

  // ── Filtered worksheets by search ──
  const filteredWs = useMemo(() => {
    if (!wsSearch.trim()) return worksheets;
    const q = wsSearch.toLowerCase();
    return worksheets.filter(
      (w) => w.name.toLowerCase().includes(q) || w.type.toLowerCase().includes(q)
    );
  }, [worksheets, wsSearch]);

  // ── Filtered calc fields by selected worksheet + search ──
  const filteredCalcs = useMemo(() => {
    let list = calcFields;
    if (selectedWs && selectedVisual) {
      const usedNames = new Set(selectedVisual.used_calculated_fields || []);
      if (usedNames.size > 0) {
        list = list.filter((cf) => usedNames.has(cf.name) || usedNames.has(cf.caption));
      }
    }
    if (calcSearch.trim()) {
      const q = calcSearch.toLowerCase();
      list = list.filter((cf) => cf.caption.toLowerCase().includes(q) || cf.name.toLowerCase().includes(q));
    }
    return list;
  }, [calcFields, selectedWs, selectedVisual, calcSearch]);

  // ── Complete Workbook Tables & Data Model ──
  const tableSet = new Set<string>();
  datasources.forEach((ds: any) => {
    if (Array.isArray(ds.tables)) ds.tables.forEach((t: string) => tableSet.add(t));
    else if (ds.name) tableSet.add(ds.name);
  });
  joins.forEach((j: any) => {
    if (j.left_table) tableSet.add(j.left_table);
    if (j.right_table) tableSet.add(j.right_table);
  });
  relationships.forEach((r: any) => {
    if (r.table1) tableSet.add(r.table1);
    if (r.table2) tableSet.add(r.table2);
  });

  const tablesList = Array.from(tableSet);
  const activeTable = tablesList.includes(selectedTable)
    ? selectedTable
    : tablesList[0] || (datasources[0]?.name || "Main Datasource");

  const activeDs = datasources.find(
    (ds: any) => ds.name === activeTable || (ds.tables && ds.tables.includes(activeTable))
  );
  const activeColsCount = activeDs?.columns ? activeDs.columns.length : 12;
  const activeCalcCount = activeDs?.calculated_field_count ?? calcFields.length;
  const activeConnectionType = activeDs?.connection_type || "Relational SQL";

  const activeRelsSet = new Set<string>();
  joins.forEach((j: any) => {
    if (j.left_table === activeTable && j.right_table) activeRelsSet.add(j.right_table);
    if (j.right_table === activeTable && j.left_table) activeRelsSet.add(j.left_table);
  });
  relationships.forEach((r: any) => {
    if (r.table1 === activeTable && r.table2) activeRelsSet.add(r.table2);
    if (r.table2 === activeTable && r.table1) activeRelsSet.add(r.table1);
  });
  const activeRelsList = Array.from(activeRelsSet);

  // ── Handlers ──
  const handleSelectWs = useCallback((name: string) => {
    setSelectedWs((prev) => (prev === name ? null : name));
    setExpandedWs((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
    setSelectedCalc(null);
  }, []);

  const toggleWsExpand = useCallback((name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    handleSelectWs(name);
  }, [handleSelectWs]);

  const toggleCalcExpand = useCallback((name: string) => {
    setExpandedCalcs((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
    setSelectedCalc(name);
  }, []);

  // ── Highlights ──
  const highlightedWsByCalc = useMemo(() => {
    if (!selectedCalc) return new Set<string>();
    return new Set(calcToWorksheets.get(selectedCalc) || []);
  }, [selectedCalc, calcToWorksheets]);

  const highlightedCalcsByWs = useMemo(() => {
    if (!selectedVisual) return new Set<string>();
    return new Set(selectedVisual.used_calculated_fields || []);
  }, [selectedVisual]);

  // ═══════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════
  return (
    <div className={styles.container}>
      {/* ── EXECUTIVE SUMMARY BAR ── */}
      <div className={styles.summaryBar}>
        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <LayoutDashboard size={16} style={{ color: "#00A8CC" }} />
            <span className={styles.statLabel}>Dashboards</span>
          </div>
          <div className={styles.statValue}>{dashboardCount}</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <BarChart3 size={16} style={{ color: "#27AE60" }} />
            <span className={styles.statLabel}>Worksheets</span>
          </div>
          <div className={styles.statValue}>{wsCount}</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <TrendingUp size={16} style={{ color: "#F2994A" }} />
            <span className={styles.statLabel}>Measures</span>
          </div>
          <div className={styles.statValue}>{measuresList.length}</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <Calculator size={16} style={{ color: "#9B51E0" }} />
            <span className={styles.statLabel}>Calculated Fields</span>
          </div>
          <div className={styles.statValue}>{calcCount}</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <Database size={16} style={{ color: "#2D9CDB" }} />
            <span className={styles.statLabel}>Data Sources</span>
          </div>
          <div className={styles.statValue}>{dsCount}</div>
        </div>
      </div>

      {/* ═══════════════════════════════════════
          MASTER-DETAIL EXPLORER GRID
          65% Worksheets | 5% Gap | 30% Calculated Fields
          ═══════════════════════════════════════ */}
      <div className={styles.explorerGrid}>
        {/* ── LEFT PANEL: Worksheets (65%) ── */}
        <div className={styles.worksheetPanel}>
          <div className={styles.panelHeader}>
            <BarChart3 size={14} style={{ color: "var(--accent-cyan)" }} />
            <h3 className={styles.panelTitle}>Worksheets / Charts</h3>
            <span className={styles.panelCount}>{filteredWs.length}</span>
          </div>
          <div className={styles.searchBox}>
            <div className={styles.searchWrapper}>
              <Search size={13} className={styles.searchIcon} />
              <input
                className={styles.searchInput}
                placeholder="Search worksheets…"
                value={wsSearch}
                onChange={(e) => setWsSearch(e.target.value)}
              />
            </div>
          </div>

          <div className={styles.cardList}>
            {filteredWs.map((ws) => {
              const isSelected = selectedWs === ws.name;
              const isHighlighted = highlightedWsByCalc.has(ws.name);
              const isExpanded = expandedWs.has(ws.name);
              const compat = getCompatibility(ws);
              const Icon = getChartIcon(ws.type);
              const color = getChartColor(ws.type);
              const wsCalcCount = (ws.used_calculated_fields || []).length;
              const wsFilterCount = (ws.filters || []).length;

              return (
                <div
                  key={ws.name}
                  className={`${styles.wsCard} ${isSelected ? styles.wsCardSelected : ""} ${isHighlighted && !isSelected ? styles.wsCardHighlighted : ""}`}
                  onClick={() => handleSelectWs(ws.name)}
                  tabIndex={0}
                  role="button"
                  onKeyDown={(e) => { if (e.key === "Enter") handleSelectWs(ws.name); }}
                >
                  <div className={styles.wsCardTop}>
                    <Icon size={14} style={{ color, flexShrink: 0 }} />
                    <span className={styles.wsName}>{ws.title || ws.name}</span>
                    <span
                      className={styles.chartTypeBadge}
                      style={{ backgroundColor: `${color}18`, color, border: `1px solid ${color}40` }}
                    >
                      {ws.type}
                    </span>
                  </div>
                  <div className={styles.wsMetaRow}>
                    {wsCalcCount > 0 && <span className={styles.wsStat}>𝑓 {wsCalcCount} Calcs</span>}
                    {wsFilterCount > 0 && <span className={styles.wsStat}>⊞ {wsFilterCount} Filters</span>}
                    <span className={styles.wsStat}>◫ {ws.dimensions?.length || 0} Dims</span>
                    <span className={styles.wsStat}>∑ {ws.measures?.length || 0} Meas</span>
                    <ChevronRight
                      size={13}
                      style={{
                        marginLeft: "auto",
                        color: "var(--text-tertiary)",
                        transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)",
                        transition: "transform 0.2s ease",
                      }}
                      onClick={(e) => toggleWsExpand(ws.name, e)}
                    />
                  </div>

                  {/* ── RICH IN-PLACE WORKSHEET INTELLIGENCE ── */}
                  {isExpanded && (
                    <div className={styles.wsExpanded} onClick={(e) => e.stopPropagation()}>
                      <div className={styles.specSectionGrid}>
                        {/* Rows / Cols Shelves */}
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>Rows & Columns Shelves</span>
                          <div className={styles.wsExpandedPills}>
                            {ws.rows_shelves && ws.rows_shelves.length > 0 ? (
                              ws.rows_shelves.map((s, i) => (
                                <span key={`r-${i}`} className={`${styles.miniPill} ${styles.miniPillShelf}`}>
                                  Row: {s.derivation ? `${s.derivation}(${s.field_name})` : s.field_name}
                                </span>
                              ))
                            ) : (
                              ws.rows?.map((r, i) => (
                                <span key={`r-${i}`} className={`${styles.miniPill} ${styles.miniPillShelf}`}>Row: {r}</span>
                              ))
                            )}
                            {ws.columns_shelves && ws.columns_shelves.length > 0 ? (
                              ws.columns_shelves.map((s, i) => (
                                <span key={`c-${i}`} className={`${styles.miniPill} ${styles.miniPillShelf}`}>
                                  Col: {s.derivation ? `${s.derivation}(${s.field_name})` : s.field_name}
                                </span>
                              ))
                            ) : (
                              ws.columns?.map((c, i) => (
                                <span key={`c-${i}`} className={`${styles.miniPill} ${styles.miniPillShelf}`}>Col: {c}</span>
                              ))
                            )}
                            {(!ws.rows?.length && !ws.columns?.length && !ws.rows_shelves?.length && !ws.columns_shelves?.length) && (
                              <span className={styles.emptyState}>No shelf fields</span>
                            )}
                          </div>
                        </div>

                        {/* Visual Mark / Specs */}
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>Visual Specification</span>
                          <div className={styles.wsExpandedPills}>
                            <span className={`${styles.miniPill} ${styles.miniPillDim}`}>Mark: {ws.mark_type || "Automatic"}</span>
                            <span className={`${styles.miniPill} ${styles.miniPillDim}`}>Source: {ws.datasource_name || "Default"}</span>
                          </div>
                        </div>
                      </div>

                      {/* Dimensions & Measures */}
                      <div className={styles.specSectionGrid}>
                        {ws.dimensions && ws.dimensions.length > 0 && (
                          <div className={styles.specBlock}>
                            <span className={styles.specBlockLabel}>Dimensions ({ws.dimensions.length})</span>
                            <div className={styles.wsExpandedPills}>
                              {ws.dimensions.map((d, i) => (
                                <span key={i} className={`${styles.miniPill} ${styles.miniPillDim}`}>{d}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {ws.measures && ws.measures.length > 0 && (
                          <div className={styles.specBlock}>
                            <span className={styles.specBlockLabel}>Measures ({ws.measures.length})</span>
                            <div className={styles.wsExpandedPills}>
                              {ws.measures.map((m, i) => (
                                <span key={i} className={`${styles.miniPill} ${styles.miniPillMeasure}`}>{m}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Filters */}
                      {ws.filters && ws.filters.length > 0 && (
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>Worksheet Filters ({ws.filters.length})</span>
                          <div className={styles.wsExpandedPills}>
                            {ws.filters.map((f, i) => (
                              <span key={i} className={`${styles.miniPill} ${styles.miniPillFilter}`}>{f}</span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Calculated Fields Used */}
                      {ws.used_calculated_fields && ws.used_calculated_fields.length > 0 && (
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>Calculated Fields Used ({ws.used_calculated_fields.length})</span>
                          <div className={styles.wsExpandedPills}>
                            {ws.used_calculated_fields.map((cf, i) => (
                              <span
                                key={i}
                                className={`${styles.miniPill} ${styles.miniPillCalc}`}
                                onClick={(e) => { e.stopPropagation(); setSelectedCalc(cf); }}
                              >
                                𝑓 {cf}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            {filteredWs.length === 0 && (
              <div className={styles.emptyState}>No worksheets match your search.</div>
            )}
          </div>
        </div>

        {/* ── RIGHT PANEL: Calculated Fields (30%) ── */}
        <div className={styles.calcPanel}>
          <div className={styles.panelHeader}>
            <Calculator size={14} style={{ color: "#9B51E0" }} />
            <h3 className={styles.panelTitle}>Calculated Fields</h3>
            <span className={styles.panelCount}>{filteredCalcs.length}</span>
          </div>

          {selectedWs && selectedVisual && (selectedVisual.used_calculated_fields || []).length > 0 && (
            <div className={styles.filterBanner}>
              <span className={styles.filterBannerText}>
                Filtered by <span className={styles.filterBannerName}>{selectedVisual.title || selectedWs}</span>
              </span>
              <button className={styles.clearFilterBtn} onClick={() => setSelectedWs(null)}>
                Clear Filter
              </button>
            </div>
          )}

          <div className={styles.searchBox}>
            <div className={styles.searchWrapper}>
              <Search size={13} className={styles.searchIcon} />
              <input
                className={styles.searchInput}
                placeholder="Search calculated fields…"
                value={calcSearch}
                onChange={(e) => setCalcSearch(e.target.value)}
              />
            </div>
          </div>

          <div className={styles.cardList}>
            {filteredCalcs.map((cf) => {
              const isExpanded = expandedCalcs.has(cf.name);
              const isSelected = selectedCalc === cf.name;
              const isHighlighted = highlightedCalcsByWs.has(cf.name);
              const complexity = calcComplexity(cf.formula);
              const referencedBy = calcToWorksheets.get(cf.name) || calcToWorksheets.get(cf.caption) || [];

              const deps: string[] = [];
              const depMatches = cf.formula.match(/\[([^\]]+)\]/g);
              if (depMatches) depMatches.forEach((m) => deps.push(m.replace(/[[\]]/g, "")));

              return (
                <div
                  key={cf.name}
                  className={`${styles.calcCard} ${isSelected ? styles.calcCardSelected : ""} ${isHighlighted && !isSelected ? styles.calcCardHighlighted : ""}`}
                  onClick={() => toggleCalcExpand(cf.name)}
                  tabIndex={0}
                  role="button"
                  onKeyDown={(e) => { if (e.key === "Enter") toggleCalcExpand(cf.name); }}
                >
                  <div className={styles.calcCardTop}>
                    <span className={styles.calcName}>{cf.caption}</span>
                    <span className={styles.calcTypeBadge}>{cf.type}</span>
                  </div>

                  {isExpanded && (
                    <div className={styles.calcExpanded} onClick={(e) => e.stopPropagation()}>
                      <span className={styles.specBlockLabel}>Formula</span>
                      <div className={styles.calcFormulaBlock}>{cf.formula || "—"}</div>
                      {deps.length > 0 && (
                        <>
                          <span className={styles.specBlockLabel}>Dependencies</span>
                          <div className={styles.calcDeps}>
                            {deps.map((d, i) => (
                              <span key={i} className={styles.depPill}>{d}</span>
                            ))}
                          </div>
                        </>
                      )}
                      {referencedBy.length > 0 && (
                        <>
                          <span className={styles.specBlockLabel}>Referenced By</span>
                          <div className={styles.calcDeps}>
                            {referencedBy.map((ws, i) => (
                              <span
                                key={i}
                                className={styles.refPill}
                                onClick={(e) => { e.stopPropagation(); handleSelectWs(ws); }}
                              >
                                {ws}
                              </span>
                            ))}
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            {filteredCalcs.length === 0 && (
              <div className={styles.emptyState}>
                {calcFields.length === 0 ? "No calculated fields in workbook." : "No fields match your search."}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════
          PREVIOUS WORKBOOK DATA MODEL VERSION
          (Interactive Diagram Canvas + Detail Inspector)
          ═══════════════════════════════════════ */}
      <div className={styles.sectionBlock}>
        <div className={styles.sectionHeader}>
          <h3 className={styles.sectionTitle}>
            <Database size={16} style={{ color: "#2D9CDB" }} /> Detected Data Model
          </h3>
          <span className={styles.subtextHint}>Click any table below to inspect schema, measures, and relationships</span>
        </div>

        <div className={styles.dataModelContainer}>
          {/* Left / Center Diagram */}
          <div className={styles.diagramCanvas}>
            <div className={styles.diagramFlow}>
              {tablesList.length > 0 ? (
                tablesList.map((tName: string, idx: number) => (
                  <div
                    key={idx}
                    className={`${styles.tableNode} ${activeTable === tName ? styles.nodeSelected : ""}`}
                    onClick={() => setSelectedTable(tName)}
                  >
                    <Database size={16} /> {tName}
                  </div>
                ))
              ) : (
                <div className={styles.tableNode}>
                  <Database size={16} /> {dashboardName} (Logical Model)
                </div>
              )}
            </div>
          </div>

          {/* Right Table Detail Panel */}
          <div className={styles.tableDetailInspector}>
            <div className={styles.inspectorHeader}>
              <Database size={16} style={{ color: "var(--accent-cyan)" }} />
              <h4>{activeTable}</h4>
            </div>
            <div className={styles.inspectorMetricsGrid}>
              <div className={styles.inspectorMetricBox}>
                <span className={styles.inspectorKey}>Columns</span>
                <span className={styles.inspectorVal}>{activeColsCount}</span>
              </div>
              <div className={styles.inspectorMetricBox}>
                <span className={styles.inspectorKey}>Calculations</span>
                <span className={styles.inspectorVal}>{activeCalcCount}</span>
              </div>
              <div className={styles.inspectorMetricBox}>
                <span className={styles.inspectorKey}>Connection</span>
                <span className={styles.inspectorVal} style={{ fontSize: "0.75rem" }}>
                  {activeConnectionType}
                </span>
              </div>
              <div className={styles.inspectorMetricBox}>
                <span className={styles.inspectorKey}>Relationships</span>
                <span className={styles.inspectorVal}>{activeRelsList.length}</span>
              </div>
            </div>

            {activeRelsList.length > 0 && (
              <div className={styles.relationshipsSection}>
                <span className={styles.inspectorKey}>Linked Tables</span>
                <div className={styles.relTagsList}>
                  {activeRelsList.map((r: string, idx: number) => (
                    <span key={idx} className={styles.relTag}>
                      ↔ {r}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
