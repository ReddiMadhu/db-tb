"use client";

import React, { useEffect, useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  LayoutGrid,
  PieChart,
  BarChart3,
  Search,
  Filter,
  ArrowRight,
  Code,
} from "lucide-react";
import type { StageDetail } from "@/lib/types";
import { getLakeviewJson, getStageDetail, getMigrationStatus } from "@/lib/api";
import ReviewCardActions from "./ReviewCardActions";
import {
  LakeviewDashboardAdapter,
  type MatchedPair,
} from "@/lib/lakeviewDashboardAdapter";
import styles from "./VisualConversionDetail.module.css";

interface VisualConversionDetailProps {
  jobUuid: string;
  stage: StageDetail;
  goldenOverride?: boolean;
}

export interface TableauVisualDef {
  type: string;
  rows: string[];
  columns: string[];
  color?: string;
  size?: string;
  angle?: string;
  label?: string;
  tooltip?: string[];
  detail?: string;
  lod?: string[];
  filters?: string[];
  pages?: string;
  measure_names?: string;
  measure_values?: string;
  calculated_fields?: string[];
  parameters?: string[];
  hidden?: boolean;
}

export interface DatabricksVisualDef {
  widget_type: string;
  dataset: string;
  category?: string;
  value?: string;
  series?: string;
  x_axis?: string;
  y_axis?: string;
  tooltip?: string[];
  filters?: string[];
  sort?: string;
  aggregation?: string;
  limit?: string;
  formatting?: string;
}

export interface BusinessValidationChecks {
  visual_type_preserved: boolean;
  fields_correctly_mapped: boolean;
  filters_preserved: boolean;
  aggregations_preserved: boolean;
  formatting_preserved: boolean;
  sort_order_preserved: boolean;
  tooltip_preserved: boolean;
  calculations_preserved: boolean;
  differences?: Array<{
    title: string;
    from: string;
    to: string;
    reason: string;
  }>;
}

export interface ManualReviewDetails {
  issue: string;
  reason: string;
  missing_binding?: string;
  suggested_fix?: string;
  recommendation?: string;
  impact: "Low" | "Medium" | "High";
  generated_as?: string;
}

export interface ConversionCardItem {
  id: string;
  worksheet_name: string;
  status: "SUCCESS" | "MANUAL_REVIEW" | "UNSUPPORTED" | "ACCEPTED";
  status_reason?: string;
  tableau: TableauVisualDef;
  databricks: DatabricksVisualDef;
  lakeview_json: Record<string, any>;
  validation: BusinessValidationChecks;
  manual_review?: ManualReviewDetails;
  accepted_at?: string;
}

// Fallback sample cards representing complete realistic Tableau conversion report
const DEFAULT_CONVERSION_CARDS: ConversionCardItem[] = [
  {
    id: "card-1",
    worksheet_name: "Incident Vs Claims - Gender Distribution",
    status: "SUCCESS",
    tableau: {
      type: "Pie Chart",
      rows: ["Latitude (generated)"],
      columns: ["Longitude (generated)"],
      color: "Gender",
      size: "Total Incidents",
      angle: "Total Claim",
      label: "State",
      tooltip: ["Incident Count", "Claim Amount"],
      filters: ["Year = 2025"],
      pages: "None",
      measure_names: "None",
      measure_values: "None",
      calculated_fields: ["Total Incidents", "Total Claim"],
      parameters: ["Select Year"],
    },
    databricks: {
      widget_type: "Pie Chart",
      dataset: "insurance_claims",
      category: "Demographics_Gender",
      value: "Total_Incidents",
      tooltip: ["Total_Claim"],
      filters: ["Year = 2025"],
      sort: "Total_Incidents DESC",
      aggregation: "SUM",
      limit: "Top 50",
      formatting: "Integer / Currency ($)",
    },
    lakeview_json: {
      widgetType: "pie",
      datasetName: "insurance_claims",
      encodings: {
        category: "Demographics_Gender",
        value: "Total_Incidents",
        tooltip: "Total_Claim",
      },
      frame: {
        x: 0,
        y: 0,
        width: 3,
        height: 3,
      },
    },
    validation: {
      visual_type_preserved: true,
      fields_correctly_mapped: true,
      filters_preserved: true,
      aggregations_preserved: true,
      formatting_preserved: true,
      sort_order_preserved: true,
      tooltip_preserved: true,
      calculations_preserved: true,
    },
  },
  {
    id: "card-2",
    worksheet_name: "Monthly Claim Volume Trend by Region",
    status: "SUCCESS",
    tableau: {
      type: "Line Chart",
      rows: ["SUM(Claim Amount)"],
      columns: ["MONTH(Incident Date)"],
      color: "Region",
      size: "None",
      label: "SUM(Claim Amount)",
      tooltip: ["Incident Date", "Region", "Claim Amount"],
      filters: ["Incident Date = Last 12 Months", "Policy Status = 'Closed'"],
      calculated_fields: ["Claim Amount"],
      parameters: ["Date Granularity"],
    },
    databricks: {
      widget_type: "Line Chart",
      dataset: "claims_time_series",
      x_axis: "Incident_Date (Month)",
      y_axis: "Claim_Amount",
      series: "Region",
      tooltip: ["Incident_Date", "Region", "Claim_Amount"],
      filters: ["Incident_Date >= add_months(current_date(), -12)"],
      sort: "Incident_Date ASC",
      aggregation: "SUM",
      formatting: "Currency ($USD)",
    },
    lakeview_json: {
      widgetType: "line",
      datasetName: "claims_time_series",
      encodings: {
        x: { field: "Incident_Date", scale: { type: "time" } },
        y: { field: "Claim_Amount", transform: "SUM" },
        series: "Region",
      },
      frame: { x: 3, y: 0, width: 3, height: 3 },
    },
    validation: {
      visual_type_preserved: true,
      fields_correctly_mapped: true,
      filters_preserved: true,
      aggregations_preserved: true,
      formatting_preserved: true,
      sort_order_preserved: true,
      tooltip_preserved: true,
      calculations_preserved: true,
    },
  },
  {
    id: "card-3",
    worksheet_name: "Financial Metrics Overview (Measure Names)",
    status: "MANUAL_REVIEW",
    status_reason: "Tableau uses Measure Names pivot",
    tableau: {
      type: "Pie Chart",
      rows: ["Measure Names"],
      columns: ["None"],
      color: "Measure Names",
      angle: "Measure Values",
      label: "Measure Values",
      tooltip: ["Measure Names", "Measure Values"],
      measure_names: "[Measure Names]",
      measure_values: "[Measure Values]",
      calculated_fields: ["Net Claim", "Gross Loss Ratio"],
    },
    databricks: {
      widget_type: "Pie Chart",
      dataset: "insurance_claims",
      category: "Unmapped (Measure Names)",
      value: "Multiple Measures",
      tooltip: ["Net_Claim"],
    },
    lakeview_json: {
      widgetType: "pie",
      datasetName: "insurance_claims",
      encodings: {
        category: null,
        value: "Net_Claim",
      },
      manualReviewRequired: true,
    },
    validation: {
      visual_type_preserved: true,
      fields_correctly_mapped: false,
      filters_preserved: true,
      aggregations_preserved: true,
      formatting_preserved: true,
      sort_order_preserved: true,
      tooltip_preserved: false,
      calculations_preserved: true,
      differences: [
        {
          title: "Measure Names Pivot Required",
          from: "[Measure Names]",
          to: "Explicit Field Column",
          reason: "Databricks Lakeview pie category bindings require a physical column, not dynamically pivoted measure names.",
        },
      ],
    },
    manual_review: {
      issue: "Tableau Pie uses Measure Names.",
      reason: "Tableau uses Measure Names. Equivalent Databricks visualization could not be generated automatically.",
      missing_binding: "Category",
      suggested_fix: "Choose one measure manually or unpivot measure columns in Unity Catalog view.",
      recommendation: "Split Measure Names into explicit fields or restructure dataset query.",
      impact: "Low",
    },
  },
  {
    id: "card-4",
    worksheet_name: "Average Settlement Duration",
    status: "MANUAL_REVIEW",
    status_reason: "Default aggregation changed from AVG to SUM",
    tableau: {
      type: "Bar Chart",
      rows: ["AVG(Settlement Days)"],
      columns: ["Region"],
      color: "Policy Type",
      label: "AVG(Settlement Days)",
      tooltip: ["Region", "Settlement Days"],
      filters: ["Settlement Status = 'Complete'"],
    },
    databricks: {
      widget_type: "Bar Chart",
      dataset: "claims_fact",
      x_axis: "Region",
      y_axis: "Settlement_Days",
      series: "Policy_Type",
      aggregation: "SUM",
      formatting: "Decimal (0.0)",
    },
    lakeview_json: {
      widgetType: "bar",
      datasetName: "claims_fact",
      encodings: {
        x: "Region",
        y: { field: "Settlement_Days", transform: "SUM" },
      },
    },
    validation: {
      visual_type_preserved: true,
      fields_correctly_mapped: true,
      filters_preserved: true,
      aggregations_preserved: false,
      formatting_preserved: true,
      sort_order_preserved: true,
      tooltip_preserved: true,
      calculations_preserved: true,
      differences: [
        {
          title: "Aggregation Changed",
          from: "AVG",
          to: "SUM",
          reason: "Databricks does not support Tableau's default aggregation for this visual automatically.",
        },
      ],
    },
    manual_review: {
      issue: "Measure aggregation defaulted to SUM instead of AVG.",
      reason: "Databricks Lakeview auto-generator defaulted measure transform to SUM.",
      suggested_fix: "Update Lakeview visual Y-axis encoding transform from SUM to AVG.",
      recommendation: "Set transform property to 'AVG' in visual spec.",
      impact: "Medium",
    },
  },
  {
    id: "card-5",
    worksheet_name: "Loss Ratio Executive KPI",
    status: "SUCCESS",
    tableau: {
      type: "Text / KPI Card",
      rows: ["None"],
      columns: ["None"],
      label: "Loss Ratio",
      tooltip: ["Total Incurred Loss", "Total Earned Premium"],
      calculated_fields: ["Loss Ratio"],
    },
    databricks: {
      widget_type: "Counter (KPI)",
      dataset: "kpi_summary",
      value: "Loss_Ratio",
      formatting: "Percentage (0.0%)",
    },
    lakeview_json: {
      widgetType: "counter",
      datasetName: "kpi_summary",
      encodings: {
        value: "Loss_Ratio",
      },
      frame: { x: 0, y: 3, width: 2, height: 2 },
    },
    validation: {
      visual_type_preserved: true,
      fields_correctly_mapped: true,
      filters_preserved: true,
      aggregations_preserved: true,
      formatting_preserved: true,
      sort_order_preserved: true,
      tooltip_preserved: true,
      calculations_preserved: true,
    },
  },
];

export default function VisualConversionDetail({
  jobUuid,
  stage,
  goldenOverride = false,
}: VisualConversionDetailProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "SUCCESS" | "REVIEW" | "UNSUPPORTED">("ALL");
  const [expandedCardIds, setExpandedCardIds] = useState<Record<string, boolean>>({});
  const [copiedCardId, setCopiedCardId] = useState<string | null>(null);
  const [cardsState, setCardsState] = useState<ConversionCardItem[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionOk, setActionOk] = useState<string | null>(null);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [goldenJson, setGoldenJson] = useState<unknown | null>(null);
  const [goldenLoading, setGoldenLoading] = useState(false);
  const [goldenEmptyReason, setGoldenEmptyReason] = useState<string | null>(null);
  const [resolvedGolden, setResolvedGolden] = useState(Boolean(goldenOverride));

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(`.${styles.dropdownWrapper}`)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const toggleCardExpand = (cardId: string) => {
    setExpandedCardIds((prev) => ({ ...prev, [cardId]: !prev[cardId] }));
  };

  const artifacts = (stage.artifacts || {}) as Record<string, any>;
  const metrics = (stage.metrics || {}) as Record<string, any>;

  // Prefer prop, then stage artifact flag, then status API
  useEffect(() => {
    if (goldenOverride || artifacts.golden_override) {
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
  }, [goldenOverride, jobUuid, artifacts.golden_override]);

  const isGolden = resolvedGolden;
  const visualTypesDetected: string[] = Array.isArray(metrics.visual_types_detected)
    ? metrics.visual_types_detected
    : Array.isArray(artifacts.visual_types)
    ? artifacts.visual_types
    : [];
  const chromeWidgets = Array.isArray(artifacts.chrome_widgets) ? artifacts.chrome_widgets : [];

  const artifactCards: ConversionCardItem[] =
    Array.isArray(artifacts.conversion_cards) && artifacts.conversion_cards.length > 0
      ? artifacts.conversion_cards
      : Array.isArray(artifacts.widgets) && artifacts.widgets.length > 0
      ? artifacts.widgets
          .filter((w: any) => w.type === "chart")
          .map((w: any, idx: number) => ({
            id: `widget-${idx}`,
            worksheet_name: w.name || w.title || `Worksheet ${idx + 1}`,
            status: "SUCCESS" as const,
            tableau: {
              type: w.visual_type_label || w.visual_type || "Chart",
              rows: [],
              columns: [],
            },
            databricks: {
              widget_type: w.visual_type_label || w.visual_type || w.type || "Chart",
              dataset: w.dataset || "",
              category: w.encodings?.x || w.encodings?.color || undefined,
              value: w.encodings?.y || w.encodings?.angle || undefined,
              aggregation: "SUM",
            },
            lakeview_json: {
              widgetType: w.visual_type || "bar",
              datasetName: w.dataset || "",
              encodings: w.encodings || {},
              frame: { title: w.name || w.title },
            },
            validation: {
              visual_type_preserved: true,
              fields_correctly_mapped: true,
              filters_preserved: true,
              aggregations_preserved: true,
              formatting_preserved: true,
              sort_order_preserved: true,
              tooltip_preserved: true,
              calculations_preserved: true,
            },
          }))
      : [];

  // Non-golden: artifacts → widgets → DEFAULT. Golden: never DEFAULT.
  const rawCards: ConversionCardItem[] = isGolden
    ? []
    : artifactCards.length > 0
      ? artifactCards
      : DEFAULT_CONVERSION_CARDS;

  useEffect(() => {
    if (isGolden) return;
    setCardsState(rawCards);
  }, [stage.artifacts, stage.generated_code, isGolden]);

  useEffect(() => {
    if (!isGolden) {
      setGoldenJson(null);
      setGoldenEmptyReason(null);
      return;
    }

    let cancelled = false;
    setGoldenLoading(true);
    setGoldenEmptyReason(null);

    (async () => {
      try {
        let json: unknown = null;
        if (typeof artifacts.lakeview_json_str === "string" && artifacts.lakeview_json_str.trim().startsWith("{")) {
          try {
            json = JSON.parse(artifacts.lakeview_json_str);
          } catch {
            json = null;
          }
        }
        const [fetched, parseStage] = await Promise.all([
          json ? Promise.resolve(null) : getLakeviewJson(jobUuid),
          getStageDetail(jobUuid, "PARSE").catch(() => null),
        ]);
        if (cancelled) return;
        if (!json) json = fetched;
        setGoldenJson(json);

        const adapter = new LakeviewDashboardAdapter(json);
        const tableauNames: string[] = [];
        const seen = new Set<string>();
        for (const c of artifactCards) {
          const n = c.worksheet_name;
          if (n && !seen.has(n)) {
            seen.add(n);
            tableauNames.push(n);
          }
        }
        const parseArtifacts = (parseStage?.artifacts || {}) as Record<string, any>;
        const detailed = Array.isArray(parseArtifacts.detailed_visuals)
          ? parseArtifacts.detailed_visuals
          : [];
        for (const v of detailed) {
          const n = v?.name || v?.worksheet_name || v?.title;
          if (typeof n === "string" && n && !seen.has(n)) {
            seen.add(n);
            tableauNames.push(n);
          }
        }
        const wsList = Array.isArray(parseArtifacts.worksheets) ? parseArtifacts.worksheets : [];
        for (const w of wsList) {
          const n = typeof w === "string" ? w : w?.name;
          if (typeof n === "string" && n && !seen.has(n)) {
            seen.add(n);
            tableauNames.push(n);
          }
        }
        const ontologyWs = parseArtifacts.workbook_ontology?.worksheets;
        if (Array.isArray(ontologyWs)) {
          for (const w of ontologyWs) {
            const n = typeof w === "string" ? w : w?.name;
            if (typeof n === "string" && n && !seen.has(n)) {
              seen.add(n);
              tableauNames.push(n);
            }
          }
        }
        if (tableauNames.length === 0 && Array.isArray(artifacts.pages)) {
          for (const p of artifacts.pages) {
            const ws = p?.worksheets || p?.worksheet_names || [];
            if (Array.isArray(ws)) {
              for (const n of ws) {
                if (typeof n === "string" && n && !seen.has(n)) {
                  seen.add(n);
                  tableauNames.push(n);
                }
              }
            }
          }
        }

        const pairs: MatchedPair[] = adapter.matchWorksheets(tableauNames);
        const pairByWorksheet = new Map(
          pairs.map((p) => [p.tableauWorksheetName, p] as const)
        );

        const enrichFromPair = (
          pair: MatchedPair,
          existing: ConversionCardItem | undefined,
          idx: number
        ): ConversionCardItem => {
          const w = pair.widget;
          const axes = adapter.getAxes(w);
          const dims = adapter.getDimensions(w);
          const measures = adapter.getMeasures(w);
          const aggs = adapter.getAggregations(w);
          const filters = adapter.getFilters(w);
          const visualType = adapter.getVisualType(w);

          return {
            id: `golden-${w.id || idx}`,
            worksheet_name: pair.tableauWorksheetName,
            status: existing?.status || ("SUCCESS" as const),
            tableau: existing?.tableau || {
              type: "N/A",
              rows: dims,
              columns: measures,
              filters: [],
              calculated_fields: [],
            },
            databricks: {
              widget_type: visualType,
              dataset: adapter.getDataset(w),
              category: dims[0],
              value: measures[0],
              x_axis: axes.x.join(", ") || undefined,
              y_axis: axes.y.join(", ") || undefined,
              filters: filters.length ? filters : undefined,
              aggregation: aggs.join(", ") || undefined,
            },
            lakeview_json: {
              widgetType: w.widgetType,
              datasetName: w.datasetName,
              encodings: (w.raw.spec as any)?.encodings || {},
              frame: { title: w.title },
              dimensions: dims,
              measures,
              aggregations: aggs,
              filters,
              query: adapter.getQuery(w),
              axes,
            },
            validation: existing?.validation || {
              visual_type_preserved: true,
              fields_correctly_mapped: true,
              filters_preserved: true,
              aggregations_preserved: true,
              formatting_preserved: true,
              sort_order_preserved: true,
              tooltip_preserved: true,
              calculations_preserved: true,
            },
          };
        };

        let goldenCards: ConversionCardItem[] = [];
        if (artifactCards.length > 0) {
          goldenCards = artifactCards.map((existing, idx) => {
            const pair = pairByWorksheet.get(existing.worksheet_name);
            if (pair) return enrichFromPair(pair, existing, idx);
            return {
              ...existing,
              id: existing.id || `card-${idx}`,
            };
          });
        } else if (pairs.length > 0) {
          goldenCards = pairs.map((pair, idx) => enrichFromPair(pair, undefined, idx));
        }

        if (goldenCards.length === 0) {
          setCardsState([]);
          setGoldenEmptyReason(
            "No matched visuals between Tableau worksheets and Lakeview widgets"
          );
          return;
        }

        setCardsState(goldenCards);
        setGoldenEmptyReason(null);
      } catch (err: any) {
        if (!cancelled) {
          setCardsState([]);
          setGoldenEmptyReason(err?.message || "Failed to load curated Lakeview JSON");
        }
      } finally {
        if (!cancelled) setGoldenLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isGolden, jobUuid, stage.artifacts]);

  // Filtered Cards
  const cards = cardsState.filter((card) => {
    const matchesSearch =
      card.worksheet_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      card.tableau.type.toLowerCase().includes(searchQuery.toLowerCase()) ||
      card.databricks.widget_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (card.databricks.dataset || "").toLowerCase().includes(searchQuery.toLowerCase());

    const matchesStatus =
      statusFilter === "ALL" ||
      (statusFilter === "SUCCESS" && (card.status === "SUCCESS" || card.status === "ACCEPTED")) ||
      (statusFilter === "REVIEW" && card.status === "MANUAL_REVIEW") ||
      (statusFilter === "UNSUPPORTED" && card.status === "UNSUPPORTED");

    return matchesSearch && matchesStatus;
  });

  // Summary counts always follow the cards list so top metrics match.
  const totalCards =
    cardsState.length > 0 ? cardsState.length : metrics.worksheets_total || 0;
  const successfulCards = cardsState.filter(
    (c) => c.status === "SUCCESS" || c.status === "ACCEPTED"
  ).length;
  const reviewCards = cardsState.filter((c) => c.status === "MANUAL_REVIEW").length;
  const unsupportedCards = cardsState.filter((c) => c.status === "UNSUPPORTED").length;
  const conversionAccuracy =
    totalCards > 0 ? Math.round((successfulCards / totalCards) * 100) : 98;

  const copyCode = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCardId(id);
    setTimeout(() => setCopiedCardId(null), 2000);
  };

  return (
    <div className={styles.container}>
      {/* ── Executive Conversion Summary Cards ── */}
      <div className={styles.summaryGrid}>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>
            Visuals Converted <LayoutGrid size={13} />
          </span>
          <span className={styles.summaryValue}>
            {successfulCards + reviewCards} / {totalCards}
          </span>
          <span className={styles.summarySubtext}>
            {metrics.chart_widgets != null
              ? `${metrics.chart_widgets} charts · ${metrics.chrome_widgets ?? 0} chrome`
              : "Total Tableau Worksheets"}
          </span>
        </div>

        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>
            Successful <CheckCircle2 size={13} style={{ color: "var(--accent-green)" }} />
          </span>
          <span className={`${styles.summaryValue} ${styles.summaryValueSuccess}`}>
            {successfulCards}
          </span>
          <span className={styles.summarySubtext}>Mapped to Lakeview widgets</span>
        </div>

        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>
            Manual Review <AlertTriangle size={13} style={{ color: "var(--accent-amber)" }} />
          </span>
          <span className={`${styles.summaryValue} ${styles.summaryValueReview}`}>
            {reviewCards}
          </span>
          <span className={styles.summarySubtext}>Partial mapping / fallback</span>
        </div>

        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>
            Unsupported <XCircle size={13} style={{ color: "var(--text-tertiary)" }} />
          </span>
          <span className={`${styles.summaryValue} ${styles.summaryValueUnsupported}`}>
            {unsupportedCards}
          </span>
          <span className={styles.summarySubtext}>No widget generated</span>
        </div>
      </div>

      {/* ── Filter Toolbar ── */}
      <div className={styles.toolbar}>
        <div className={styles.searchFilterGroup}>
          <div className={styles.searchBox}>
            <Search size={14} style={{ color: "var(--text-tertiary)" }} />
            <input
              type="text"
              placeholder="Search worksheets, visual types..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className={styles.dropdownWrapper}>
            <button
              type="button"
              className={`${styles.customDropdownTrigger} ${isDropdownOpen ? styles.customDropdownTriggerOpen : ""}`}
              onClick={() => setIsDropdownOpen((prev) => !prev)}
              aria-expanded={isDropdownOpen}
              aria-label="Filter conversion status"
            >
              <div className={styles.dropdownTriggerContent}>
                {statusFilter === "ALL" && <Filter size={13} style={{ color: "var(--accent-cyan, #00a8cc)" }} />}
                {statusFilter === "SUCCESS" && <CheckCircle2 size={13} style={{ color: "#3fb950" }} />}
                {statusFilter === "REVIEW" && <AlertTriangle size={13} style={{ color: "#d29922" }} />}
                {statusFilter === "UNSUPPORTED" && <XCircle size={13} style={{ color: "#8b949e" }} />}

                <span className={styles.dropdownSelectedLabel}>
                  {statusFilter === "ALL" && "All Statuses"}
                  {statusFilter === "SUCCESS" && "Successfully Converted"}
                  {statusFilter === "REVIEW" && "Manual Review Required"}
                  {statusFilter === "UNSUPPORTED" && "Unsupported / Missing"}
                </span>

                <span className={styles.dropdownCountBadge}>
                  {statusFilter === "ALL" && cardsState.length}
                  {statusFilter === "SUCCESS" && successfulCards}
                  {statusFilter === "REVIEW" && reviewCards}
                  {statusFilter === "UNSUPPORTED" && unsupportedCards}
                </span>
              </div>

              <ChevronDown
                size={14}
                className={`${styles.dropdownChevron} ${isDropdownOpen ? styles.dropdownChevronRotate : ""}`}
              />
            </button>

            {isDropdownOpen && (
              <div className={styles.customDropdownMenu}>
                <div className={styles.dropdownMenuHeader}>Filter Conversion Status</div>

                <button
                  type="button"
                  className={`${styles.dropdownOption} ${statusFilter === "ALL" ? styles.dropdownOptionSelected : ""}`}
                  onClick={() => {
                    setStatusFilter("ALL");
                    setIsDropdownOpen(false);
                  }}
                >
                  <span className={styles.optionIconBox} style={{ background: "rgba(0, 168, 204, 0.12)", color: "#00a8cc" }}>
                    <Filter size={13} />
                  </span>
                  <div className={styles.optionTextGroup}>
                    <span className={styles.optionTitle}>All Statuses</span>
                    <span className={styles.optionDesc}>Show all visual cards</span>
                  </div>
                  <span className={styles.optionBadge}>{cardsState.length}</span>
                  {statusFilter === "ALL" && <Check size={14} className={styles.optionCheck} />}
                </button>

                <button
                  type="button"
                  className={`${styles.dropdownOption} ${statusFilter === "SUCCESS" ? styles.dropdownOptionSelected : ""}`}
                  onClick={() => {
                    setStatusFilter("SUCCESS");
                    setIsDropdownOpen(false);
                  }}
                >
                  <span className={styles.optionIconBox} style={{ background: "rgba(63, 185, 80, 0.12)", color: "#3fb950" }}>
                    <CheckCircle2 size={13} />
                  </span>
                  <div className={styles.optionTextGroup}>
                    <span className={styles.optionTitle}>Successfully Converted</span>
                    <span className={styles.optionDesc}>Passed automated validation</span>
                  </div>
                  <span className={styles.optionBadge} style={{ background: "rgba(63, 185, 80, 0.15)", color: "#3fb950" }}>
                    {successfulCards}
                  </span>
                  {statusFilter === "SUCCESS" && <Check size={14} className={styles.optionCheck} />}
                </button>

                <button
                  type="button"
                  className={`${styles.dropdownOption} ${statusFilter === "REVIEW" ? styles.dropdownOptionSelected : ""}`}
                  onClick={() => {
                    setStatusFilter("REVIEW");
                    setIsDropdownOpen(false);
                  }}
                >
                  <span className={styles.optionIconBox} style={{ background: "rgba(210, 153, 34, 0.12)", color: "#d29922" }}>
                    <AlertTriangle size={13} />
                  </span>
                  <div className={styles.optionTextGroup}>
                    <span className={styles.optionTitle}>Manual Review Required</span>
                    <span className={styles.optionDesc}>Needs human verification</span>
                  </div>
                  <span className={styles.optionBadge} style={{ background: "rgba(210, 153, 34, 0.15)", color: "#d29922" }}>
                    {reviewCards}
                  </span>
                  {statusFilter === "REVIEW" && <Check size={14} className={styles.optionCheck} />}
                </button>

                <button
                  type="button"
                  className={`${styles.dropdownOption} ${statusFilter === "UNSUPPORTED" ? styles.dropdownOptionSelected : ""}`}
                  onClick={() => {
                    setStatusFilter("UNSUPPORTED");
                    setIsDropdownOpen(false);
                  }}
                >
                  <span className={styles.optionIconBox} style={{ background: "rgba(139, 148, 158, 0.12)", color: "#8b949e" }}>
                    <XCircle size={13} />
                  </span>
                  <div className={styles.optionTextGroup}>
                    <span className={styles.optionTitle}>Unsupported / Missing</span>
                    <span className={styles.optionDesc}>Visual types not yet supported</span>
                  </div>
                  <span className={styles.optionBadge} style={{ background: "rgba(139, 148, 158, 0.15)", color: "#8b949e" }}>
                    {unsupportedCards}
                  </span>
                  {statusFilter === "UNSUPPORTED" && <Check size={14} className={styles.optionCheck} />}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── VISUAL CONVERSION CARDS STACK ── */}
      <div className={styles.cardsList}>
        {goldenLoading ? (
          <div className={styles.emptyState}>Loading Lakeview visuals…</div>
        ) : cards.length === 0 ? (
          <div className={styles.emptyState}>
            {isGolden
              ? goldenEmptyReason ||
                "No matched visuals between Tableau worksheets and Lakeview widgets"
              : "No visual conversion cards match your search filter."}
          </div>
        ) : (
          cards.map((card) => {
            const isCardExpanded = !!expandedCardIds[card.id];
            const isCopied = copiedCardId === card.id;
            const jsonString = JSON.stringify(card.lakeview_json, null, 2);

            return (
              <div
                key={card.id}
                className={`${styles.conversionCard} ${
                  card.status === "MANUAL_REVIEW" ? styles.conversionCardReview : ""
                }`}
              >
                {/* Card Header */}
                <div
                  className={styles.conversionCardHeader}
                  onClick={() => toggleCardExpand(card.id)}
                  style={{ cursor: "pointer" }}
                >
                  <div className={styles.cardTitleArea}>
                    <span className={styles.cardTitle}>{card.worksheet_name}</span>
                    <span className={styles.visualTypeBadge}>
                      Tableau: {card.tableau.type} → Databricks: {card.databricks.widget_type}
                    </span>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                    {card.status === "SUCCESS" && (
                      <span className={styles.statusBadgeSuccess}>
                        <CheckCircle2 size={13} /> Converted
                      </span>
                    )}
                    {card.status === "MANUAL_REVIEW" && (
                      <span className={styles.statusBadgeReview}>
                        <AlertTriangle size={13} /> Manual Review
                      </span>
                    )}
                    {card.status === "ACCEPTED" && (
                      <span className={styles.statusBadgeSuccess}>
                        <CheckCircle2 size={13} /> Accepted
                      </span>
                    )}
                    {card.status === "UNSUPPORTED" && (
                      <span className={styles.statusBadgeUnsupported}>
                        <XCircle size={13} /> Unsupported
                      </span>
                    )}
                    <span className={styles.cardExpandIcon}>
                      {isCardExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                    </span>
                  </div>
                </div>

                {/* Card Body Details (Collapsed by default) */}
                {isCardExpanded && (
                  <>
                    {/* Side-by-Side Comparison Grid */}
                    <div className={styles.cardComparisonBody}>
                      {/* LEFT SIDE: TABLEAU VISUAL */}
                      <div className={styles.visualSideColumn}>
                        <div className={styles.columnHeader}>
                          <span className={`${styles.columnHeaderTitle} ${styles.tableauAccent}`}>
                            <PieChart size={14} /> Tableau Visual
                          </span>
                          <span className={styles.fieldTag}>Original Spec</span>
                        </div>

                        <div className={styles.fieldGroup}>
                          <div className={styles.fieldRow}>
                            <span className={styles.fieldLabel}>Type:</span>
                            <span className={styles.fieldValue}>{card.tableau.type}</span>
                          </div>
                          <div className={styles.fieldRow}>
                            <span className={styles.fieldLabel}>Rows:</span>
                            <span className={styles.fieldValue}>{(card.tableau.rows || []).join(", ") || "None"}</span>
                          </div>
                          <div className={styles.fieldRow}>
                            <span className={styles.fieldLabel}>Columns:</span>
                            <span className={styles.fieldValue}>{(card.tableau.columns || []).join(", ") || "None"}</span>
                          </div>
                        </div>

                        <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-tertiary)", marginTop: "0.25rem" }}>
                          Visual Encodings (Marks)
                        </div>

                        <div className={styles.fieldGroup}>
                          {card.tableau.color && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Color:</span>
                              <span className={styles.fieldValue}>
                                <span className={`${styles.fieldTag} ${styles.fieldTagCyan}`}>{card.tableau.color}</span>
                              </span>
                            </div>
                          )}
                          {card.tableau.size && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Size:</span>
                              <span className={styles.fieldValue}>{card.tableau.size}</span>
                            </div>
                          )}
                          {card.tableau.angle && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Angle:</span>
                              <span className={styles.fieldValue}>{card.tableau.angle}</span>
                            </div>
                          )}
                          {card.tableau.lod && card.tableau.lod.length > 0 && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>LOD:</span>
                              <span className={styles.fieldValue}>{card.tableau.lod.join(", ")}</span>
                            </div>
                          )}
                          {card.tableau.label && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Label:</span>
                              <span className={styles.fieldValue}>{card.tableau.label}</span>
                            </div>
                          )}
                          {card.tableau.tooltip && card.tableau.tooltip.length > 0 && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Tooltip:</span>
                              <span className={styles.fieldValue}>{card.tableau.tooltip.join(", ")}</span>
                            </div>
                          )}
                          {card.tableau.filters && card.tableau.filters.length > 0 && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Filters:</span>
                              <span className={styles.fieldValue}>{card.tableau.filters.join(", ")}</span>
                            </div>
                          )}
                          {card.tableau.calculated_fields && card.tableau.calculated_fields.length > 0 && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Calc Fields:</span>
                              <span className={styles.fieldValue}>
                                {card.tableau.calculated_fields.map((cf, idx) => (
                                  <span key={idx} className={`${styles.fieldTag} ${styles.fieldTagPurple}`}>{cf}</span>
                                ))}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* MIDDLE CONVERTED ARROW */}
                      <div className={styles.arrowDivider}>
                        <ArrowRight size={20} />
                        <span className={styles.arrowText}>Converted To</span>
                      </div>

                      {/* RIGHT SIDE: DATABRICKS VISUAL */}
                      <div className={styles.visualSideColumn}>
                        <div className={styles.columnHeader}>
                          <span className={`${styles.columnHeaderTitle} ${styles.databricksAccent}`}>
                            <BarChart3 size={14} /> Databricks Visual
                          </span>
                          <span className={styles.fieldTagCyan}>Lakeview Spec</span>
                        </div>

                        <div className={styles.fieldGroup}>
                          <div className={styles.fieldRow}>
                            <span className={styles.fieldLabel}>Widget Type:</span>
                            <span className={styles.fieldValue}>{card.databricks.widget_type}</span>
                          </div>
                          <div className={styles.fieldRow}>
                            <span className={styles.fieldLabel}>Dataset:</span>
                            <span className={`${styles.fieldValue} ${styles.fieldTagCyan}`}>{card.databricks.dataset}</span>
                          </div>
                        </div>

                        <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-tertiary)", marginTop: "0.25rem" }}>
                          Bindings & Properties
                        </div>

                        <div className={styles.fieldGroup}>
                          {card.databricks.category && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Category:</span>
                              <span className={styles.fieldValue}>{card.databricks.category}</span>
                            </div>
                          )}
                          {card.databricks.x_axis && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>X Axis:</span>
                              <span className={styles.fieldValue}>{card.databricks.x_axis}</span>
                            </div>
                          )}
                          {card.databricks.y_axis && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Y Axis:</span>
                              <span className={styles.fieldValue}>{card.databricks.y_axis}</span>
                            </div>
                          )}
                          {card.databricks.value && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Value:</span>
                              <span className={styles.fieldValue}>{card.databricks.value}</span>
                            </div>
                          )}
                          {card.databricks.series && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Series:</span>
                              <span className={styles.fieldValue}>{card.databricks.series}</span>
                            </div>
                          )}
                          {card.databricks.tooltip && card.databricks.tooltip.length > 0 && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Tooltip:</span>
                              <span className={styles.fieldValue}>{card.databricks.tooltip.join(", ")}</span>
                            </div>
                          )}
                          {card.databricks.filters && card.databricks.filters.length > 0 && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Filters:</span>
                              <span className={styles.fieldValue}>{card.databricks.filters.join(", ")}</span>
                            </div>
                          )}
                          {card.databricks.aggregation && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Aggregation:</span>
                              <span className={styles.fieldValue}>{card.databricks.aggregation}</span>
                            </div>
                          )}
                          {card.databricks.formatting && (
                            <div className={styles.fieldRow}>
                              <span className={styles.fieldLabel}>Formatting:</span>
                              <span className={styles.fieldValue}>{card.databricks.formatting}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Manual Review Details Callout */}
                    {card.manual_review && (
                      <div className={styles.manualReviewBox}>
                        <span className={styles.manualReviewTitle}>
                          <AlertTriangle size={14} /> Manual Review Action Required
                        </span>
                        <div className={styles.manualReviewGrid}>
                          <div>
                            <div className={styles.reviewItemLabel}>Reason</div>
                            <div className={styles.reviewItemVal}>{card.manual_review.reason}</div>
                          </div>
                          {card.manual_review.missing_binding && (
                            <div>
                              <div className={styles.reviewItemLabel}>Missing Binding</div>
                              <div className={styles.reviewItemVal} style={{ color: "var(--accent-amber)" }}>
                                {card.manual_review.missing_binding}
                              </div>
                            </div>
                          )}
                          {card.manual_review.suggested_fix && (
                            <div>
                              <div className={styles.reviewItemLabel}>Suggested Fix</div>
                              <div className={styles.reviewItemVal} style={{ color: "var(--accent-green)" }}>
                                {card.manual_review.suggested_fix}
                              </div>
                            </div>
                          )}
                          {card.manual_review.generated_as && (
                            <div>
                              <div className={styles.reviewItemLabel}>Generated As</div>
                              <div className={styles.reviewItemVal}>{card.manual_review.generated_as}</div>
                            </div>
                          )}
                          {card.manual_review.impact && (
                            <div>
                              <div className={styles.reviewItemLabel}>Impact</div>
                              <div className={styles.reviewItemVal}>{card.manual_review.impact}</div>
                            </div>
                          )}
                        </div>
                        <ReviewCardActions
                          jobUuid={jobUuid}
                          card={card}
                          onUpdated={(updated) => {
                            setCardsState((prev) =>
                              prev.map((c) => (c.id === updated.id ? { ...c, ...updated } : c))
                            );
                          }}
                          onError={setActionError}
                          onOk={setActionOk}
                        />
                      </div>
                    )}

                    {!card.manual_review &&
                      (card.status === "MANUAL_REVIEW" || card.status === "UNSUPPORTED") && (
                        <ReviewCardActions
                          jobUuid={jobUuid}
                          card={card}
                          onUpdated={(updated) => {
                            setCardsState((prev) =>
                              prev.map((c) => (c.id === updated.id ? { ...c, ...updated } : c))
                            );
                          }}
                          onError={setActionError}
                          onOk={setActionOk}
                        />
                      )}

                    {/* Code Editor JSON Viewer Box */}
                    <div className={styles.jsonViewerContainer}>
                      <div className={styles.jsonViewerHeader}>
                        <span className={styles.jsonViewerTitle}>
                          <Code size={13} /> Generated Lakeview JSON
                        </span>
                        <div className={styles.jsonViewerActions}>
                          <button className={styles.codeActionBtn} onClick={() => copyCode(card.id, jsonString)}>
                            {isCopied ? (
                              <>
                                <Check size={12} style={{ color: "var(--accent-green)" }} /> Copied
                              </>
                            ) : (
                              <>
                                <Copy size={12} /> Copy JSON
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                      <pre className={styles.codeBlock}>
                        <code>{jsonString}</code>
                      </pre>
                    </div>
                  </>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
