"use client";

import React, { useState } from "react";
import {
  Clock,
  ChevronDown,
  ChevronRight,
  Download,
  AlertTriangle,
  CheckCircle2,
  Database,
  Table,
  Sparkles,
  Code,
  LayoutGrid,
  ShieldCheck,
  FileText,
  PieChart,
  BarChart3,
  TrendingUp,
  Cpu,
  Layers,
  ArrowRight,
  Gauge,
  HelpCircle,
} from "lucide-react";
import InlineMappingPanel from "./InlineMappingPanel";
import RelationshipDiagram from "./RelationshipDiagram";
import PublishPanel from "./PublishPanel";
import DashboardVisualPreview from "./DashboardVisualPreview";
import FormulaConversionCard from "./FormulaConversionCard";
import VisualCompatibilityMatrix from "./VisualCompatibilityMatrix";
import ParseStageDetail from "./ParseStageDetail";
import CalcLogicConversionDetail from "./CalcLogicConversionDetail";
import VisualConversionDetail from "./VisualConversionDetail";
import DeploymentReviewDetail from "./DeploymentReviewDetail";
import { getStageDetail } from "@/lib/api";
import { getStageConfig } from "@/lib/pipeline.config";
import type { StageDetail, FormulaConversionItem, VisualCompatibilityItem } from "@/lib/types";
import styles from "./StageDetailPanel.module.css";

interface StageDetailPanelProps {
  jobUuid: string;
  stageId?: string;
  stage?: StageDetail | null;
  loading?: boolean;
  onExecute?: () => void;
  onSelectStage?: (stageId: string) => void;
  goldenOverride?: boolean;
}

export default function StageDetailPanel({
  jobUuid,
  stageId,
  stage: propStage,
  loading: propLoading = false,
  onExecute,
  onSelectStage,
  goldenOverride = false,
}: StageDetailPanelProps) {
  const [stage, setStage] = useState<StageDetail | null>(propStage || null);
  const [fetching, setFetching] = useState<boolean>(false);
  const [openTechnical, setOpenTechnical] = useState<boolean>(false);

  React.useEffect(() => {
    if (propStage) {
      setStage(propStage);
      return;
    }
    if (jobUuid && stageId) {
      setFetching(true);
      getStageDetail(jobUuid, stageId)
        .then((data) => setStage(data))
        .catch(() => setStage(null))
        .finally(() => setFetching(false));
    }
  }, [jobUuid, stageId, propStage]);

  const isLoading = propLoading || fetching;

  if (isLoading) {
    return (
      <div className={styles.panel}>
        <div className={styles.skeleton} style={{ width: "40%" }} />
        <div className={styles.skeleton} style={{ width: "70%" }} />
        <div className={styles.skeleton} style={{ width: "100%", height: "180px" }} />
      </div>
    );
  }

  if (!stage) {
    return (
      <div className={styles.panel}>
        <div className={styles.waitingState}>
          Select a stage from the pipeline above to view details.
        </div>
      </div>
    );
  }

  const config = getStageConfig(stage.stage_id);
  const isWaiting = stage.status === "WAITING";
  const artifacts = (stage.artifacts || {}) as Record<string, any>;
  const metrics = (stage.metrics || {}) as Record<string, any>;

  // Compute confidence score
  const confidenceScore = metrics.migration_confidence || (stage.errors.length > 0 ? 72 : stage.warnings.length > 0 ? 88 : 96);

  if (stage.stage_id === "PARSE") {
    return (
      <div className={styles.panel}>
        <ParseStageDetail
          jobUuid={jobUuid}
          stage={stage}
          onSelectNextStage={onSelectStage}
        />
      </div>
    );
  }

  if (stage.stage_id === "SOURCE_MAPPING") {
    return (
      <div className={styles.panel}>
        <InlineMappingPanel jobUuid={jobUuid} onExecute={onExecute} />
      </div>
    );
  }

  if (stage.stage_id === "CALC_LOGIC_CONVERSION") {
    return (
      <div className={styles.panel}>
        <CalcLogicConversionDetail
          jobUuid={jobUuid}
          stage={stage}
          goldenOverride={goldenOverride}
        />
      </div>
    );
  }

  if (stage.stage_id === "LAYOUT_GENERATION") {
    return (
      <div className={styles.panel}>
        <VisualConversionDetail
          jobUuid={jobUuid}
          stage={stage}
          goldenOverride={goldenOverride}
        />
      </div>
    );
  }

  if (stage.stage_id === "SCHEMA_VALIDATION" || stage.stage_id === "PUBLISH") {
    return (
      <div className={styles.panel}>
        <DeploymentReviewDetail
          jobUuid={jobUuid}
          stage={stage}
          onSelectNextStage={onSelectStage}
          goldenOverride={goldenOverride}
        />
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      {/* ── Stage Header ── */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h2 className={styles.title}>
            {stage.stage_number}. {stage.stage_name}
          </h2>
          <p className={styles.description}>{config?.description || ""}</p>
        </div>
        <div className={styles.headerRight}>
          {stage.duration_ms !== null && (
            <span className={styles.duration}>
              <Clock size={13} /> {stage.duration_ms}ms
            </span>
          )}
        </div>
      </div>

      {/* ── Waiting State ── */}
      {isWaiting && stage.stage_id !== "SOURCE_MAPPING" && stage.stage_id !== "PUBLISH" && (
        <div className={styles.waitingState}>
          This stage is waiting to run.
          <div className={styles.waitingHint}>
            Click <strong>Execute Pipeline</strong> above to compile calculations, model UBIM, and generate Lakeview specs.
          </div>
        </div>
      )}

      {(!isWaiting || stage.stage_id === "SOURCE_MAPPING" || stage.stage_id === "PUBLISH") && (
        <>
          {/* ── 3-PANEL BUSINESS WORKSPACE ── */}
          <div className={styles.workspaceGrid}>
            
            {/* ── LEFT PANEL: Business Summary ── */}
            <div className={styles.leftPanel}>
              <div className={styles.businessCard}>
                <div className={styles.businessCardTitle}>
                  <Sparkles size={14} style={{ color: "var(--accent-cyan)" }} /> Business Summary
                </div>
                <div className={styles.overviewMetricList}>
                  {stage.stage_id === "UPLOAD" && (
                    <>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Workbook Name</span>
                        <span className={styles.overviewMetricVal}>{String(metrics.workbook_name || artifacts.workbook_name || "Workbook")}</span>
                      </div>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Dashboards Found</span>
                        <span className={styles.overviewMetricVal}>{String(metrics.dashboards_found ?? (artifacts.dashboards_count || 0))}</span>
                      </div>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Worksheets</span>
                        <span className={styles.overviewMetricVal}>{String(metrics.worksheets_count ?? (artifacts.worksheets ? artifacts.worksheets.length : 0))}</span>
                      </div>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Visualizations</span>
                        <span className={styles.overviewMetricVal}>{String(metrics.visualizations_count ?? (artifacts.detailed_visuals ? artifacts.detailed_visuals.length : 0))}</span>
                      </div>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Data Sources</span>
                        <span className={styles.overviewMetricVal}>{String(metrics.datasources_count ?? (artifacts.datasources ? artifacts.datasources.length : 0))}</span>
                      </div>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Calculated Fields</span>
                        <span className={styles.overviewMetricVal}>{String(metrics.calculated_fields_count ?? (artifacts.calculated_fields ? artifacts.calculated_fields.length : 0))}</span>
                      </div>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Parameters</span>
                        <span className={styles.overviewMetricVal}>{String(metrics.parameters_count ?? 0)}</span>
                      </div>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Filters</span>
                        <span className={styles.overviewMetricVal}>{String(metrics.filters_count ?? 0)}</span>
                      </div>
                    </>
                  )}

                  {stage.stage_id === "PARSE" && (
                    <>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Dashboard Name</span>
                        <span className={styles.overviewMetricVal}>{String(artifacts.dashboard_name || artifacts.dashboard_title || "Dashboard")}</span>
                      </div>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Business Subject</span>
                        <span className={styles.overviewMetricVal}>{String(artifacts.business_subject || artifacts.domain || "Analytics")}</span>
                      </div>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Worksheets Parsed</span>
                        <span className={styles.overviewMetricVal}>{String(metrics.worksheets_parsed ?? (artifacts.worksheets ? artifacts.worksheets.length : 0))}</span>
                      </div>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Measures Detected</span>
                        <span className={styles.overviewMetricVal}>{String(metrics.measures_count ?? (artifacts.measures ? artifacts.measures.length : 0))}</span>
                      </div>
                      <div className={styles.overviewMetricRow}>
                        <span className={styles.overviewMetricKey}>Dimensions Detected</span>
                        <span className={styles.overviewMetricVal}>{String(metrics.dimensions_count ?? (artifacts.dimensions ? artifacts.dimensions.length : 0))}</span>
                      </div>
                    </>
                  )}

                  {stage.stage_id !== "UPLOAD" && stage.stage_id !== "PARSE" && (
                    <>
                      {stage.input_summary && (
                        <div className={styles.overviewMetricRow}>
                          <span className={styles.overviewMetricKey}>Input</span>
                          <span className={styles.overviewMetricVal} style={{ fontSize: "0.75rem" }}>{stage.input_summary}</span>
                        </div>
                      )}
                      {stage.output_summary && (
                        <div className={styles.overviewMetricRow}>
                          <span className={styles.overviewMetricKey}>Status</span>
                          <span className={styles.overviewMetricVal} style={{ color: "var(--accent-green)", fontSize: "0.75rem" }}>{stage.output_summary}</span>
                        </div>
                      )}
                      {Object.entries(metrics).slice(0, 6).map(([k, v]) => (
                        <div key={k} className={styles.overviewMetricRow}>
                          <span className={styles.overviewMetricKey}>{k.replace(/_/g, " ")}</span>
                          <span className={styles.overviewMetricVal}>{String(v)}</span>
                        </div>
                      ))}
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* ── CENTER PANEL: Main Output & Interactive View ── */}
            <div className={styles.centerPanel}>
              
              {/* 1. UPLOAD NODE: DASHBOARD PREVIEW */}
              {stage.stage_id === "UPLOAD" && (
                <div className={styles.businessCard}>
                  <div className={styles.businessCardTitle}>
                    <LayoutGrid size={15} style={{ color: "var(--accent-cyan)" }} />
                    Dashboard Preview — {artifacts.dashboard_preview_name || "Workbook Insights"}
                  </div>
                  <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                    Contains the following business elements extracted from Tableau:
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                    {Array.isArray(artifacts.contained_visual_types) ? (
                      artifacts.contained_visual_types.map((v: string, idx: number) => (
                        <span key={idx} className={styles.nameTag} style={{ color: "var(--accent-cyan)", borderColor: "rgba(0, 168, 204, 0.3)" }}>
                          {v}
                        </span>
                      ))
                    ) : (
                      <>
                        <span className={styles.nameTag} style={{ color: "var(--accent-cyan)" }}>✓ KPI Cards</span>
                        <span className={styles.nameTag} style={{ color: "var(--accent-cyan)" }}>✓ Bar Charts</span>
                        <span className={styles.nameTag} style={{ color: "var(--accent-cyan)" }}>✓ Pie Charts</span>
                        <span className={styles.nameTag} style={{ color: "var(--accent-cyan)" }}>✓ Interactive Filters</span>
                        <span className={styles.nameTag} style={{ color: "var(--accent-cyan)" }}>✓ Parameters</span>
                        <span className={styles.nameTag} style={{ color: "var(--accent-cyan)" }}>✓ Calculated Metrics</span>
                      </>
                    )}
                  </div>
                </div>
              )}

              {/* 2. PARSE NODE: WHAT WE UNDERSTOOD */}
              {stage.stage_id === "PARSE" && (
                <div className={styles.businessCard}>
                  <div className={styles.businessCardTitle}>
                    <CheckCircle2 size={15} style={{ color: "var(--accent-green)" }} /> What We Understood
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
                    <div>
                      <h4 style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", textTransform: "uppercase", marginBottom: "0.4rem" }}>Detected Visuals</h4>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
                        {Array.isArray(artifacts.detected_visuals) && artifacts.detected_visuals.map((v: string, idx: number) => (
                          <span key={idx} className={styles.nameTag}>{v}</span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <h4 style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", textTransform: "uppercase", marginBottom: "0.4rem" }}>Key Measures</h4>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
                        {Array.isArray(artifacts.measures) && artifacts.measures.slice(0, 6).map((m: string, idx: number) => (
                          <span key={idx} className={styles.nameTag} style={{ color: "var(--accent-purple)" }}>{m}</span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {Array.isArray(artifacts.joins) && artifacts.joins.length > 0 && (
                    <div>
                      <h4 style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", textTransform: "uppercase", marginBottom: "0.4rem" }}>Detected Data Relationships</h4>
                      <RelationshipDiagram joins={artifacts.joins} />
                    </div>
                  )}
                </div>
              )}

              {/* 3. SOURCE MAPPING STAGE (INLINE MAPPING WORKFLOW) */}
              {stage.stage_id === "SOURCE_MAPPING" && (
                <div className={styles.businessCard}>
                  <InlineMappingPanel jobUuid={jobUuid} onExecute={onExecute} />
                </div>
              )}

              {/* 4. CALC LOGIC CONVERSION — handled by early return above */}

              {/* 5. CALC LOGIC CONVERSION STAGE */}
              {stage.stage_id === "CALC_LOGIC_CONVERSION" && (
                <div>
                  <h4 style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.75rem" }}>
                    Transpiled Databricks SQL Formulas
                  </h4>
                  {Array.isArray(artifacts.conversions) && artifacts.conversions.slice(0, 15).map((c: FormulaConversionItem, idx: number) => (
                    <FormulaConversionCard key={idx} item={c} />
                  ))}
                </div>
              )}

              {/* 6. LAYOUT GENERATION STAGE (INTERACTIVE DASHBOARD PREVIEW) */}
              {stage.stage_id === "LAYOUT_GENERATION" && (
                <div>
                  <h4 style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.75rem" }}>
                    Generated Databricks Lakeview Dashboard Preview
                  </h4>
                  <DashboardVisualPreview pages={artifacts.pages} />
                </div>
              )}

              {/* 7. SCHEMA VALIDATION STAGE */}
              {stage.stage_id === "SCHEMA_VALIDATION" && (
                <div>
                  <h4 style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.75rem" }}>
                    Visual & Schema Compatibility Matrix
                  </h4>
                  <VisualCompatibilityMatrix items={artifacts.visual_compatibility_matrix} />
                </div>
              )}

              {/* 8. PUBLISH STAGE */}
              {stage.stage_id === "PUBLISH" && (
                <PublishPanel
                  jobUuid={jobUuid}
                  initialArtifacts={artifacts}
                  onPublished={() => {
                    if (stageId && jobUuid) {
                      getStageDetail(jobUuid, stageId).then((data) => setStage(data)).catch(() => {});
                    }
                  }}
                />
              )}
            </div>

            {/* ── RIGHT PANEL: Issues & Alerts ── */}
            {(stage.errors.length > 0 || stage.warnings.length > 0) && (
              <div className={styles.rightPanel}>
                <div className={styles.businessCard}>
                  <div className={styles.businessCardTitle}>
                    <AlertTriangle size={14} style={{ color: "var(--accent-amber)" }} /> Issues & Warnings
                  </div>
                  {stage.errors.map((err, idx) => (
                    <div key={`err-${idx}`} className={styles.issueError} style={{ marginBottom: "0.5rem" }}>
                      {err}
                    </div>
                  ))}
                  {stage.warnings.map((warn, idx) => (
                    <div key={`warn-${idx}`} className={styles.issueWarn} style={{ marginBottom: "0.5rem" }}>
                      {warn}
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>
        </>
      )}
    </div>
  );
}

