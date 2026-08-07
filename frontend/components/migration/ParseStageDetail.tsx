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
  caption?: string;
  description?: string;
  hidden?: boolean;
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
  used_parameters?: string[];
  used_sets?: string[];
  used_groups?: string[];
  used_hierarchies?: string[];
  used_table_calcs?: string[];
  used_lod_calcs?: string[];
  rows_shelves?: { field_name: string; derivation: string | null; raw: string }[];
  columns_shelves?: { field_name: string; derivation: string | null; raw: string }[];
  pages_shelf?: { field_name: string; derivation: string | null; raw: string }[];
  measure_values_used?: boolean;
  encodings?: { channel: string; field_name: string; field_type: string; aggregation: string | null; derivation: string | null }[];
  mark_properties?: { channel: string; field_name: string; palette_name?: string; palette_colors?: string[]; show_mark_labels?: boolean; label_alignment?: string }[];
  axes?: { shelf: string; field_name: string; title?: string; range_type?: string; reversed?: boolean; logarithmic?: boolean }[];
  legends?: { field_name: string; legend_type?: string; title?: string; position?: string; hidden?: boolean }[];
  tooltip_fields?: { field_name: string; aggregation?: string; custom_label?: string; has_viz_in_tooltip?: boolean; viz_worksheet?: string }[];
  analytics?: { overlay_type: string; field_name?: string; label?: string; scope?: string }[];
  sorts?: { field_name: string; direction: string; sort_type: string }[];
  filter_details?: { field_name: string; filter_type: string; min_value?: string | null; max_value?: string | null; is_context_filter: boolean; is_global: boolean; scope: string; ui_mode?: string }[];
  related_actions?: string[];
  dashboard_consumers?: string[];
  complexity?: { score: string; numeric_score: number; field_count: number; calculation_count: number; lod_count: number; lod_channel_count?: number; table_calc_count: number; filter_count: number; parameter_count: number; action_count: number; analytics_overlay_count: number; unsupported_features: string[]; conversion_notes: string[] };
  map_style?: string;
  uuid?: string;
}

interface CalcField {
  name: string;
  caption: string;
  formula: string;
  type: string;
  datasource: string;
  return_type?: string;
  dependencies?: string[];
  is_used?: boolean;
  internal_name?: string;
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
  const [showOntology, setShowOntology] = useState(false);

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
    return artifacts.calculated_fields.map((cf: any) => {
      const rawName = (cf.name || cf.internal_name || "").replace(/^\[|\]$/g, "");
      const internalName = (cf.internal_name || "").replace(/^\[|\]$/g, "").trim() || undefined;
      let cap = cf.caption;
      if (!cap || cap === "Calculation") {
        // Never strip Calculation_<digits> down to bare "Calculation"
        if (/^calculation_\d+/i.test(rawName)) {
          cap = undefined;
        } else {
          const stripped = rawName.replace(/_\d{8,}$/, "").trim();
          if (stripped && !/^calculation$/i.test(stripped)) {
            cap = stripped;
          }
        }
      }
      if (!cap || cap.toLowerCase().startsWith("calculation_")) {
        cap = (cf.caption && cf.caption !== "Calculation" ? cf.caption : null) || rawName;
      }
      if (/^calculation$/i.test(cap || "")) {
        cap = rawName;
      }
      return {
        name: rawName || cap || "Calculated Field",
        caption: cap || rawName || "Calculated Field",
        formula: cf.formula || "",
        type: cf.type || cf.formula_type || "STANDARD",
        datasource: cf.datasource || "Default",
        return_type: cf.return_type || undefined,
        dependencies: Array.isArray(cf.dependencies) ? cf.dependencies : undefined,
        is_used: typeof cf.is_used === "boolean" ? cf.is_used : undefined,
        internal_name: internalName,
      };
    });
  }, [artifacts]);

  const measuresList: string[] = Array.isArray(artifacts.measures) ? artifacts.measures : [];
  const joins = Array.isArray(artifacts.joins) ? artifacts.joins : [];
  const relationships = Array.isArray(artifacts.relationships) ? artifacts.relationships : [];
  const datasources = Array.isArray(artifacts.datasources) ? artifacts.datasources : [];

  const dashboardName = artifacts.dashboard_name || "Workbook Dashboard";
  const dashboardFilters = Array.isArray(artifacts.dashboard_filters) ? artifacts.dashboard_filters : [];
  const dashboardLegends = Array.isArray(artifacts.dashboard_legends) ? artifacts.dashboard_legends : [];
  const workbookActions = Array.isArray(artifacts.actions) ? artifacts.actions : [];
  const ontology = (artifacts.workbook_ontology || null) as Record<string, any> | null;
  const ontologyDashboard = Array.isArray(ontology?.dashboards) ? ontology.dashboards[0] : null;
  const ontologyWorkbook = ontology?.workbook || null;
  const ontologyDs = Array.isArray(ontology?.datasources) ? ontology.datasources[0] : null;

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

  // ── Name to caption lookup map for resolving Calculation_* IDs ──
  const calcNameMap = useMemo(() => {
    const map = new Map<string, string>();
    const addKey = (key: string | undefined, cap: string) => {
      if (!key || !cap || cap === "Calculation") return;
      const clean = key.replace(/^\[|\]$/g, "").trim();
      if (clean) map.set(clean, cap);
      map.set(key, cap);
    };

    calcFields.forEach((cf) => {
      const cap = cf.caption && cf.caption !== "Calculation" ? cf.caption : cf.name;
      if (!cap || cap === "Calculation" || /^calculation_\d+/i.test(cap)) return;

      addKey(cf.name, cap);
      addKey(cf.caption, cap);
      addKey(cf.internal_name, cap);

      const cleanName = (cf.name || "").replace(/^\[|\]$/g, "").trim();
      if (cleanName) {
        const stripped = cleanName.replace(/_\d{8,}$/, "").trim();
        if (stripped && !/^calculation$/i.test(stripped)) {
          map.set(stripped, cap);
        }
        const match = cleanName.match(/Calculation_\d+/i);
        if (match) map.set(match[0], cap);
      }

      if (cf.internal_name) {
        const match = cf.internal_name.match(/Calculation_\d+/i);
        if (match) map.set(match[0], cap);
      }
    });
    return map;
  }, [calcFields]);

  const resolveFieldName = useCallback(
    (field: string): string => {
      if (!field) return "";
      const clean = field.replace(/^\[|\]$/g, "").trim();

      if (calcNameMap.has(clean) && calcNameMap.get(clean) !== "Calculation") {
        return calcNameMap.get(clean)!;
      }
      if (calcNameMap.has(field) && calcNameMap.get(field) !== "Calculation") {
        return calcNameMap.get(field)!;
      }

      const unquoted = clean
        .replace(/^(usr|none|sum|avg|cnt|cntd|ctd|min|max|attr|med|yr|qr|mn|dy|wk):/i, "")
        .replace(/:(nk|qk|ok|tk)$/i, "")
        .trim();

      if (calcNameMap.has(unquoted) && calcNameMap.get(unquoted) !== "Calculation") {
        return calcNameMap.get(unquoted)!;
      }

      const calcMatch = unquoted.match(/Calculation_\d+/i);
      if (calcMatch && calcNameMap.has(calcMatch[0])) {
        const mapped = calcNameMap.get(calcMatch[0]);
        if (mapped && mapped !== "Calculation") return mapped;
      }

      const stripped = unquoted.replace(/_\d{8,}$/, "").trim();
      if (
        stripped &&
        !/^calculation$/i.test(stripped) &&
        calcNameMap.has(stripped) &&
        calcNameMap.get(stripped) !== "Calculation"
      ) {
        return calcNameMap.get(stripped)!;
      }

      // Never return bare "Calculation" from digit-stripping; keep full ID
      if (stripped && !/^calculation(_\d+)?$/i.test(stripped) && !stripped.toLowerCase().startsWith("calculation_")) {
        return stripped;
      }

      return clean;
    },
    [calcNameMap]
  );

  // ── Build reverse lookup: calc field name/caption → worksheet names ──
  const calcToWorksheets = useMemo(() => {
    const map = new Map<string, string[]>();
    const addLink = (key: string, wsName: string) => {
      if (!key) return;
      if (!map.has(key)) map.set(key, []);
      if (!map.get(key)!.includes(wsName)) map.get(key)!.push(wsName);
    };

    worksheets.forEach((ws) => {
      const rawWsFields = [
        ...(ws.used_calculated_fields || []),
        ...(ws.columns || []),
        ...(ws.rows || []),
        ...(ws.filters || []),
        ...(ws.encodings || []).map((e) => e.field_name),
        ...(ws.rows_shelves || []).map((s) => s.field_name),
        ...(ws.columns_shelves || []).map((s) => s.field_name),
      ];

      const matchedKeys = new Set<string>();
      rawWsFields.forEach((f) => {
        matchedKeys.add(f);
        const resolved = resolveFieldName(f);
        if (resolved) matchedKeys.add(resolved);
      });

      calcFields.forEach((cf) => {
        if (
          matchedKeys.has(cf.name) ||
          matchedKeys.has(cf.caption) ||
          (cf.internal_name && matchedKeys.has(cf.internal_name))
        ) {
          addLink(cf.name, ws.name);
          addLink(cf.caption, ws.name);
          if (cf.internal_name) addLink(cf.internal_name, ws.name);
        }
      });
    });
    return map;
  }, [worksheets, calcFields, resolveFieldName]);

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
      // Strict filter: only calcs listed in this worksheet's used_calculated_fields
      const usedKeys = new Set<string>();
      (selectedVisual.used_calculated_fields || []).forEach((f) => {
        usedKeys.add(f);
        const resolved = resolveFieldName(f);
        if (resolved) usedKeys.add(resolved);
      });

      list = list.filter(
        (cf) =>
          usedKeys.has(cf.name) ||
          usedKeys.has(cf.caption) ||
          (cf.internal_name != null && usedKeys.has(cf.internal_name))
      );
    }

    if (calcSearch.trim()) {
      const q = calcSearch.toLowerCase();
      list = list.filter((cf) => cf.caption.toLowerCase().includes(q) || cf.name.toLowerCase().includes(q));
    }
    return list;
  }, [calcFields, selectedWs, selectedVisual, calcSearch, resolveFieldName]);

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
    const keys = new Set<string>();
    (selectedVisual.used_calculated_fields || []).forEach((f) => {
      keys.add(f);
      const resolved = resolveFieldName(f);
      if (resolved) keys.add(resolved);
    });
    return keys;
  }, [selectedVisual, resolveFieldName]);

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
              const wsMeasCount = (ws.measures || []).filter((m) => {
                const resolved = resolveFieldName(m);
                return resolved && !/^calculation(_\d+)?$/i.test(resolved);
              }).length;

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
                    <div className={styles.wsNameWrapper}>
                      <span className={styles.wsName}>{ws.name}</span>
                      {ws.title && ws.title !== ws.name ? (
                        <span className={styles.wsTitleSub} title={`Canvas Title: ${ws.title}`}>
                          ({ws.title})
                        </span>
                      ) : null}
                    </div>
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
                    <span className={styles.wsStat}>∑ {wsMeasCount} Meas</span>
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
                          <span className={styles.specBlockLabel}>Axis & Shelf Layout (Rows/Cols)</span>
                          <div className={styles.wsExpandedPills}>
                            {ws.rows_shelves && ws.rows_shelves.length > 0 ? (
                              ws.rows_shelves.map((s, i) => (
                                <span key={`r-${i}`} className={`${styles.miniPill} ${styles.miniPillShelf}`}>
                                  Row: {s.derivation ? `${s.derivation}(${resolveFieldName(s.field_name)})` : resolveFieldName(s.field_name)}
                                </span>
                              ))
                            ) : (
                              ws.rows?.map((r, i) => (
                                <span key={`r-${i}`} className={`${styles.miniPill} ${styles.miniPillShelf}`}>Row: {resolveFieldName(r)}</span>
                              ))
                            )}
                            {ws.columns_shelves && ws.columns_shelves.length > 0 ? (
                              ws.columns_shelves.map((s, i) => (
                                <span key={`c-${i}`} className={`${styles.miniPill} ${styles.miniPillShelf}`}>
                                  Col: {s.derivation ? `${s.derivation}(${resolveFieldName(s.field_name)})` : resolveFieldName(s.field_name)}
                                </span>
                              ))
                            ) : (
                              ws.columns?.map((c, i) => (
                                <span key={`c-${i}`} className={`${styles.miniPill} ${styles.miniPillShelf}`}>Col: {resolveFieldName(c)}</span>
                              ))
                            )}
                            {(!ws.rows?.length && !ws.columns?.length && !ws.rows_shelves?.length && !ws.columns_shelves?.length) && (
                              <span className={styles.emptyState}>No shelf fields</span>
                            )}
                          </div>
                        </div>

                        {/* Visual Mark / Specs */}
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>Visual Properties & Source Dataset</span>
                          <div className={styles.wsExpandedPills}>
                            <span className={`${styles.miniPill} ${styles.miniPillDim}`}>Mark: {ws.mark_type || "Automatic"}</span>
                            <span className={`${styles.miniPill} ${styles.miniPillDim}`}>Source: {ws.datasource_name || "Default"}</span>
                            {ws.map_style ? (
                              <span className={`${styles.miniPill} ${styles.miniPillDim}`}>Map: {ws.map_style}</span>
                            ) : null}
                            {ws.uuid ? (
                              <span className={`${styles.miniPill} ${styles.miniPillShelf}`} title={ws.uuid}>UUID</span>
                            ) : null}
                          </div>
                        </div>
                      </div>

                      {/* Mark encodings (color / size / lod / angle …) */}
                      {ws.encodings && ws.encodings.length > 0 && (
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>Encodings & Aesthetics ({ws.encodings.length})</span>
                          <div className={styles.wsExpandedPills}>
                            {ws.encodings.map((enc, i) => (
                              <span
                                key={i}
                                className={`${styles.miniPill} ${enc.channel === "lod" ? styles.miniPillLod : styles.miniPillShelf}`}
                              >
                                {enc.channel}: {enc.aggregation ? `${enc.aggregation}(${resolveFieldName(enc.field_name)})` : resolveFieldName(enc.field_name)}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Dimensions & Measures */}
                      <div className={styles.specSectionGrid}>
                        {ws.dimensions && ws.dimensions.length > 0 && (
                          <div className={styles.specBlock}>
                            <span className={styles.specBlockLabel}>Dimensions (Grouping Attributes) ({ws.dimensions.length})</span>
                            <div className={styles.wsExpandedPills}>
                              {ws.dimensions.map((d, i) => (
                                <span key={i} className={`${styles.miniPill} ${styles.miniPillDim}`}>{resolveFieldName(d)}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {ws.measures && ws.measures.length > 0 && (
                          <div className={styles.specBlock}>
                            {(() => {
                              const visibleMeasures = ws.measures
                                .map((m) => ({ raw: m, resolved: resolveFieldName(m) }))
                                .filter(
                                  ({ resolved }) =>
                                    resolved && !/^calculation(_\d+)?$/i.test(resolved)
                                );
                              return (
                                <>
                                  <span className={styles.specBlockLabel}>
                                    Measures (Numerical Metrics) ({visibleMeasures.length})
                                  </span>
                                  <div className={styles.wsExpandedPills}>
                                    {visibleMeasures.map(({ raw, resolved }, i) => {
                                      const isCalc =
                                        calcNameMap.has(raw) ||
                                        calcNameMap.has(resolved) ||
                                        (ws.used_calculated_fields || []).some(
                                          (u) =>
                                            resolveFieldName(u) === resolved ||
                                            u === resolved ||
                                            u === raw
                                        );
                                      return (
                                        <span
                                          key={i}
                                          className={`${styles.miniPill} ${isCalc ? styles.miniPillCalc : styles.miniPillMeasure}`}
                                          onClick={(e) => {
                                            if (isCalc) {
                                              e.stopPropagation();
                                              setSelectedCalc(resolved);
                                            }
                                          }}
                                          style={isCalc ? { cursor: "pointer" } : undefined}
                                        >
                                          {resolved}
                                        </span>
                                      );
                                    })}
                                  </div>
                                </>
                              );
                            })()}
                          </div>
                        )}
                      </div>

                      {/* Filters */}
                      {(ws.filter_details?.length || ws.filters?.length) ? (
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>
                            Worksheet Filters & Slicers ({ws.filter_details?.length || ws.filters?.length || 0})
                          </span>
                          <div className={styles.wsExpandedPills}>
                            {ws.filter_details && ws.filter_details.length > 0
                              ? ws.filter_details.map((f, i) => (
                                  <span key={i} className={`${styles.miniPill} ${styles.miniPillFilter}`} title={f.scope}>
                                    {resolveFieldName(f.field_name)}
                                    <span className={styles.filterTypeTag}>{f.filter_type}</span>
                                    {f.filter_type === "quantitative" && (f.min_value != null || f.max_value != null)
                                      ? ` [${f.min_value ?? "…"} – ${f.max_value ?? "…"}]`
                                      : ""}
                                  </span>
                                ))
                              : ws.filters.map((f, i) => (
                                  <span key={i} className={`${styles.miniPill} ${styles.miniPillFilter}`}>{resolveFieldName(f)}</span>
                                ))}
                          </div>
                        </div>
                      ) : null}

                      {/* Analytics Overlays */}
                      {ws.analytics && ws.analytics.length > 0 && (
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>Analytics & Reference Lines ({ws.analytics.length})</span>
                          <div className={styles.wsExpandedPills}>
                            {ws.analytics.map((a, i) => (
                              <span key={i} className={`${styles.miniPill} ${styles.miniPillShelf}`}>
                                {a.label || a.overlay_type} {a.field_name ? `(${a.field_name})` : ""}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Tooltip Fields */}
                      {ws.tooltip_fields && ws.tooltip_fields.length > 0 && (
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>Tooltips & Hover Fields ({ws.tooltip_fields.length})</span>
                          <div className={styles.wsExpandedPills}>
                            {ws.tooltip_fields.map((tf, i) => (
                              <span key={i} className={`${styles.miniPill} ${styles.miniPillDim}`}>
                                {tf.aggregation ? `${tf.aggregation}(${tf.field_name})` : tf.field_name}
                                {tf.has_viz_in_tooltip ? ` [Viz in Tooltip: ${tf.viz_worksheet}]` : ""}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Semantic Dependencies (Params, Sets, Groups, LODs) */}
                      {(ws.used_parameters?.length || ws.used_sets?.length || ws.used_groups?.length || ws.used_lod_calcs?.length || ws.used_table_calcs?.length) ? (
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>Logic Dependencies (Params, Sets, Groups, LODs)</span>
                          <div className={styles.wsExpandedPills}>
                            {ws.used_parameters?.map((p, i) => (
                              <span key={`p-${i}`} className={`${styles.miniPill} ${styles.miniPillCalc}`}>Param: {p}</span>
                            ))}
                            {ws.used_sets?.map((s, i) => (
                              <span key={`s-${i}`} className={`${styles.miniPill} ${styles.miniPillFilter}`}>Set: {s}</span>
                            ))}
                            {ws.used_groups?.map((g, i) => (
                              <span key={`g-${i}`} className={`${styles.miniPill} ${styles.miniPillDim}`}>Group: {g}</span>
                            ))}
                            {ws.used_lod_calcs?.map((l, i) => (
                              <span key={`l-${i}`} className={`${styles.miniPill} ${styles.miniPillMeasure}`}>LOD: {l}</span>
                            ))}
                            {ws.used_table_calcs?.map((tc, i) => (
                              <span key={`tc-${i}`} className={`${styles.miniPill} ${styles.miniPillMeasure}`}>TableCalc: {tc}</span>
                            ))}
                          </div>
                        </div>
                      ) : null}

                      {/* Dashboard Interactions */}
                      {(ws.dashboard_consumers?.length || ws.related_actions?.length) ? (
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>Dashboard Interactions & Actions</span>
                          <div className={styles.wsExpandedPills}>
                            {ws.dashboard_consumers?.map((db, i) => (
                              <span key={`db-${i}`} className={`${styles.miniPill} ${styles.miniPillShelf}`}>📊 Dashboard: {db}</span>
                            ))}
                            {ws.related_actions?.map((act, i) => (
                              <span key={`act-${i}`} className={`${styles.miniPill} ${styles.miniPillFilter}`}>⚡ Action: {act}</span>
                            ))}
                          </div>
                        </div>
                      ) : null}

                      {/* Calculated Fields Used */}
                      {ws.used_calculated_fields && ws.used_calculated_fields.length > 0 && (
                        <div className={styles.specBlock}>
                          <span className={styles.specBlockLabel}>Calculated Fields Used ({ws.used_calculated_fields.length})</span>
                          <div className={styles.wsExpandedPills}>
                            {ws.used_calculated_fields.map((cf, i) => {
                              const resolved = resolveFieldName(cf);
                              return (
                                <span
                                  key={i}
                                  className={`${styles.miniPill} ${styles.miniPillCalc}`}
                                  onClick={(e) => { e.stopPropagation(); setSelectedCalc(resolved); }}
                                  style={{ cursor: "pointer" }}
                                >
                                  𝑓 {resolved}
                                </span>
                              );
                            })}
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
                Filtered by <span className={styles.filterBannerName}>{selectedVisual.name || selectedWs}</span>
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
              const isSelected =
                selectedCalc === cf.name ||
                selectedCalc === cf.caption ||
                (cf.internal_name != null && selectedCalc === cf.internal_name);
              const isHighlighted =
                highlightedCalcsByWs.has(cf.name) ||
                highlightedCalcsByWs.has(cf.caption) ||
                (cf.internal_name != null && highlightedCalcsByWs.has(cf.internal_name));
              const complexity = calcComplexity(cf.formula);
              const referencedBy =
                calcToWorksheets.get(cf.name) ||
                calcToWorksheets.get(cf.caption) ||
                (cf.internal_name ? calcToWorksheets.get(cf.internal_name) : undefined) ||
                [];

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
                    {cf.return_type ? (
                      <span className={styles.calcTypeBadge}>{cf.return_type}</span>
                    ) : null}
                    {cf.type && cf.type !== "STANDARD" ? (
                      <span className={styles.calcTypeBadge}>{cf.type}</span>
                    ) : null}
                  </div>

                  {isExpanded && (
                    <div className={styles.calcExpanded} onClick={(e) => e.stopPropagation()}>
                      <span className={styles.specBlockLabel}>Formula</span>
                      <div className={styles.calcFormulaBlock}>{cf.formula || "—"}</div>
                      {(cf.dependencies?.length || deps.length) > 0 && (
                        <>
                          <span className={styles.specBlockLabel}>Dependencies</span>
                          <div className={styles.calcDeps}>
                            {(cf.dependencies && cf.dependencies.length > 0 ? cf.dependencies : deps).map((d, i) => (
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
          DASHBOARD CONTROLS + ACTIONS
          ═══════════════════════════════════════ */}
      {(dashboardFilters.length > 0 || dashboardLegends.length > 0 || workbookActions.length > 0) && (
        <div className={styles.sectionBlock}>
          <div className={styles.sectionHeader}>
            <h3 className={styles.sectionTitle}>
              <Filter size={16} style={{ color: "#F2994A" }} /> Dashboard Controls — {dashboardName}
            </h3>
            <span className={styles.subtextHint}>
              Quick filters, legends, and workbook actions from Tableau layout
            </span>
          </div>
          <div className={styles.dashControlsGrid}>
            {dashboardFilters.length > 0 && (
              <div className={styles.specBlock}>
                <span className={styles.specBlockLabel}>Filter Cards ({dashboardFilters.length})</span>
                <div className={styles.wsExpandedPills}>
                  {dashboardFilters.map((fc: any, i: number) => (
                    <span key={i} className={`${styles.miniPill} ${styles.miniPillFilter}`}>
                      #{fc.id} {fc.field}{fc.mode ? ` · ${fc.mode}` : ""}
                      {fc.worksheet_owner ? ` ← ${fc.worksheet_owner}` : ""}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {dashboardLegends.length > 0 && (
              <div className={styles.specBlock}>
                <span className={styles.specBlockLabel}>Legend Cards ({dashboardLegends.length})</span>
                <div className={styles.wsExpandedPills}>
                  {dashboardLegends.map((lg: any, i: number) => (
                    <span key={i} className={`${styles.miniPill} ${styles.miniPillDim}`}>
                      #{lg.id} {lg.field} · {lg.legend_type || "color"}
                      {lg.worksheet_owner ? ` ← ${lg.worksheet_owner}` : ""}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {workbookActions.length > 0 && (
              <div className={styles.specBlock}>
                <span className={styles.specBlockLabel}>Actions ({workbookActions.length})</span>
                <div className={styles.wsExpandedPills}>
                  {workbookActions.map((act: any, i: number) => (
                    <span key={i} className={`${styles.miniPill} ${styles.miniPillCalc}`}>
                      {act.caption || act.name}: {act.action_type || act.type}
                      {act.field ? ` · ${act.field}` : ""}
                      {act.activation_type ? ` · ${act.activation_type}` : ""}
                      {act.target ? ` → ${act.target}` : ""}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════
          WORKBOOK ONTOLOGY
          ═══════════════════════════════════════ */}
      {ontology && (
        <div className={styles.sectionBlock}>
          <div className={styles.sectionHeader}>
            <h3 className={styles.sectionTitle}>
              <Layers size={16} style={{ color: "#9B51E0" }} /> Workbook Ontology
            </h3>
            <button
              type="button"
              className={styles.clearFilterBtn}
              onClick={() => setShowOntology((v) => !v)}
            >
              {showOntology ? "Hide details" : "Show details"}
            </button>
          </div>
          <div className={styles.ontologySummary}>
            {ontologyWorkbook && (
              <span className={styles.ontologyChip}>
                v{ontologyWorkbook.tableau_version}
                {ontologyWorkbook.build_version ? ` · ${String(ontologyWorkbook.build_version).split(" ")[0]}` : ""}
                {ontologyWorkbook.style_theme ? ` · theme ${ontologyWorkbook.style_theme}` : ""}
              </span>
            )}
            {ontologyWorkbook?.repository_location?.site && (
              <span className={styles.ontologyChip}>site: {ontologyWorkbook.repository_location.site}</span>
            )}
            {ontologyDs?.live_or_extract && (
              <span className={styles.ontologyChip}>
                {ontologyDs.live_or_extract}
                {ontologyDs.extract?.rows_inserted != null ? ` · ${ontologyDs.extract.rows_inserted} rows` : ""}
              </span>
            )}
            {ontologyDashboard?.uuid && (
              <span className={styles.ontologyChip} title={ontologyDashboard.uuid}>
                dash UUID · zones {ontologyDashboard.zone_count ?? "—"}
              </span>
            )}
            {ontologyDashboard?.sizing_mode && (
              <span className={styles.ontologyChip}>sizing: {ontologyDashboard.sizing_mode}</span>
            )}
            {ontologyDashboard?.table_background && (
              <span className={styles.ontologyChip}>bg {ontologyDashboard.table_background}</span>
            )}
          </div>
          {showOntology && (
            <div className={styles.ontologyDetail}>
              {Array.isArray(ontologyDashboard?.text_zones) && ontologyDashboard.text_zones.length > 0 && (
                <div className={styles.specBlock}>
                  <span className={styles.specBlockLabel}>Text Zones</span>
                  <div className={styles.wsExpandedPills}>
                    {ontologyDashboard.text_zones.map((tz: any, i: number) => (
                      <span key={i} className={`${styles.miniPill} ${styles.miniPillShelf}`}>
                        #{tz.zone_id} “{tz.content}” · {tz.font} {tz.font_size}pt {tz.color}
                        {tz.bold ? " Bold" : ""}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {ontologyDashboard?.layout_hierarchy && (
                <div className={styles.specBlock}>
                  <span className={styles.specBlockLabel}>Layout Hierarchy</span>
                  <pre className={styles.ontologyTree}>{ontologyDashboard.layout_hierarchy}</pre>
                </div>
              )}
              {ontologyDs?.extract?.hyper_file && (
                <div className={styles.specBlock}>
                  <span className={styles.specBlockLabel}>Extract</span>
                  <div className={styles.wsExpandedPills}>
                    <span className={`${styles.miniPill} ${styles.miniPillDim}`}>{ontologyDs.extract.hyper_file}</span>
                    {ontologyDs.extract.update_time && (
                      <span className={`${styles.miniPill} ${styles.miniPillDim}`}>{ontologyDs.extract.update_time}</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

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
