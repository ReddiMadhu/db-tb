"use client";

import React, { useState } from "react";
import {
  Clock,
  ChevronDown,
  ChevronRight,
  Download,
  Terminal,
  AlertTriangle,
  CheckCircle2,
  FileCode,
  Layers,
  Database,
  Table,
  Cpu,
  Sparkles,
  ExternalLink,
  Code,
  LayoutGrid,
  ShieldCheck,
  FileText,
} from "lucide-react";
import StatusBadge from "@/components/ui/StatusBadge";
import InlineMappingPanel from "./InlineMappingPanel";
import RelationshipDiagram from "./RelationshipDiagram";
import { getStageDetail } from "@/lib/api";
import { getStageConfig } from "@/lib/pipeline.config";
import type { StageDetail, StageStatus } from "@/lib/types";
import styles from "./StageDetailPanel.module.css";

interface StageDetailPanelProps {
  jobUuid: string;
  stageId?: string;
  stage?: StageDetail | null;
  loading?: boolean;
  onExecute?: () => void;
}

export default function StageDetailPanel({
  jobUuid,
  stageId,
  stage: propStage,
  loading: propLoading = false,
  onExecute,
}: StageDetailPanelProps) {
  const [stage, setStage] = useState<StageDetail | null>(propStage || null);
  const [fetching, setFetching] = useState<boolean>(false);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    artifacts: true,
    logs: false,
    mapping: true,
    relationships: true,
    databricks: true,
    code: true,
  });

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

  const toggleSection = (key: string) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const isLoading = propLoading || fetching;

  if (isLoading) {
    return (
      <div className={styles.panel}>
        <div className={styles.skeleton} style={{ width: "40%" }} />
        <div className={styles.skeleton} style={{ width: "70%" }} />
        <div className={styles.skeleton} style={{ width: "100%", height: "120px" }} />
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
  const artifacts = stage.artifacts || {};
  const metrics = stage.metrics || {};

  return (
    <div className={styles.panel}>
      {/* ── Header ── */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h2 className={styles.title}>
            {stage.stage_number}. {stage.stage_name}
          </h2>
          <p className={styles.description}>{config?.description || ""}</p>
        </div>
        <div className={styles.headerRight}>
          {stage.duration_ms !== null && stage.duration_ms !== undefined && (
            <span className={styles.duration}>
              <Clock size={12} /> {stage.duration_ms}ms
            </span>
          )}
          <StatusBadge status={stage.status} />
        </div>
      </div>

      {/* ── Waiting State ── */}
      {isWaiting && (
        <div className={styles.waitingState}>
          This stage is waiting to run.
          <div className={styles.waitingHint}>
            Execute the pipeline to run this stage and generate output artifacts.
          </div>
        </div>
      )}

      {!isWaiting && (
        <>
          {/* ── Summary Row ── */}
          {(stage.input_summary || stage.output_summary) && (
            <div className={styles.summaryRow}>
              {stage.input_summary && (
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>Input</span>
                  <span className={styles.summaryValue}>{stage.input_summary}</span>
                </div>
              )}
              {stage.output_summary && (
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>Output</span>
                  <span className={styles.summaryValueGreen}>{stage.output_summary}</span>
                </div>
              )}
            </div>
          )}

          {/* ── KPI Badges ── */}
          {Object.keys(metrics).length > 0 && (
            <div className={styles.kpiBadges}>
              {Object.entries(metrics).map(([key, value]) => {
                if (typeof value === "object" && value !== null) return null;
                const formattedKey = key.replace(/_/g, " ");
                return (
                  <div key={key} className={styles.kpiBadge}>
                    <span className={styles.kpiValue}>
                      {typeof value === "boolean" ? (value ? "PASS" : "FAIL") : String(value)}
                    </span>
                    <span className={styles.kpiLabel}>{formattedKey}</span>
                  </div>
                );
              })}
            </div>
          )}

          {/* ── STAGE SPECIFIC ARTIFACT RENDERERS ── */}

          {/* 1. UPLOAD STAGE */}
          {stage.stage_id === "UPLOAD" && (
            <>
              {Array.isArray(artifacts.sheets) && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("sheets")}>
                    <span>Worksheets ({artifacts.sheets.length})</span>
                    {openSections.sheets !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.sheets !== false && (
                    <div className={styles.sectionBody}>
                      <div className={styles.nameList}>
                        {artifacts.sheets.map((name: any, idx: number) => (
                          <span key={idx} className={styles.nameTag}>
                            <Table size={12} className={styles.nameTagIcon} /> {String(name)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {Array.isArray(artifacts.dashboards) && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("dashboards")}>
                    <span>Dashboards ({artifacts.dashboards.length})</span>
                    {openSections.dashboards !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.dashboards !== false && (
                    <div className={styles.sectionBody}>
                      <div className={styles.nameList}>
                        {artifacts.dashboards.map((name: any, idx: number) => (
                          <span key={idx} className={styles.nameTag}>
                            <LayoutGrid size={12} className={styles.nameTagIcon} /> {String(name)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {Array.isArray(artifacts.datasources) && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("datasources")}>
                    <span>Datasources ({artifacts.datasources.length})</span>
                    {openSections.datasources !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.datasources !== false && (
                    <div className={styles.sectionBody}>
                      <div className={styles.nameList}>
                        {artifacts.datasources.map((name: any, idx: number) => (
                          <span key={idx} className={styles.nameTag}>
                            <Database size={12} className={styles.nameTagIcon} /> {String(name)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {Array.isArray(artifacts.embedded_files) && artifacts.embedded_files.length > 0 && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("embedded")}>
                    <span>Embedded Files ({artifacts.embedded_files.length})</span>
                    {openSections.embedded !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.embedded !== false && (
                    <div className={styles.sectionBody}>
                      <div className={styles.nameList}>
                        {artifacts.embedded_files.map((file: any, idx: number) => (
                          <span key={idx} className={styles.nameTag}>
                            <FileText size={12} className={styles.nameTagIcon} />{" "}
                            {typeof file === "object" ? file.filename || file.archive_path : String(file)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* 2. PARSE STAGE */}
          {stage.stage_id === "PARSE" && (
            <>
              {/* Databricks connection auto-discovery banner */}
              {artifacts.databricks_discovery && (
                <div className={styles.detectionBanner}>
                  <div className={styles.detectionIcon}>
                    <Sparkles size={18} />
                  </div>
                  <div className={styles.detectionInfo}>
                    <div className={styles.detectionTitle}>Databricks Unity Catalog Connection Detected</div>
                    <div className={styles.detectionDesc}>
                      Auto-discovered Unity Catalog objects in Tableau connection settings.
                    </div>
                  </div>
                </div>
              )}

              {Array.isArray(artifacts.calculated_fields) && artifacts.calculated_fields.length > 0 && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("calcFields")}>
                    <span>Parsed Calculated Fields ({artifacts.calculated_fields.length})</span>
                    {openSections.calcFields !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.calcFields !== false && (
                    <div className={styles.sectionBody}>
                      <table className={styles.formulaTable}>
                        <thead>
                          <tr>
                            <th>Field Name</th>
                            <th>Datasource</th>
                            <th>Formula</th>
                            <th>Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {artifacts.calculated_fields.slice(0, 50).map((cf: any, idx: number) => (
                            <tr key={idx}>
                              <td style={{ fontWeight: 600 }}>{cf.caption || cf.name}</td>
                              <td style={{ color: "var(--text-tertiary)" }}>{cf.datasource}</td>
                              <td className={styles.formulaCell} title={cf.formula}>
                                {cf.formula}
                              </td>
                              <td>
                                <span
                                  className={
                                    cf.type === "LOD"
                                      ? styles.typeLod
                                      : cf.type === "TABLE_CALC"
                                      ? styles.typeTableCalc
                                      : styles.typeStandard
                                  }
                                >
                                  {cf.type || "STANDARD"}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Relationships / Joins */}
              {Array.isArray(artifacts.joins) && artifacts.joins.length > 0 && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("relationships")}>
                    <span>Data Model Joins ({artifacts.joins.length})</span>
                    {openSections.relationships !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.relationships !== false && (
                    <div className={styles.sectionBody}>
                      <RelationshipDiagram joins={artifacts.joins} />
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* 3. CALC DEEP DIVE STAGE */}
          {stage.stage_id === "CALC_DEEP_DIVE" && (
            <>
              {Array.isArray(artifacts.calculated_fields) && artifacts.calculated_fields.length > 0 && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("calcDeep")}>
                    <span>Analyzed Formulas & Dependencies ({artifacts.calculated_fields.length})</span>
                    {openSections.calcDeep !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.calcDeep !== false && (
                    <div className={styles.sectionBody}>
                      <table className={styles.formulaTable}>
                        <thead>
                          <tr>
                            <th>Field Name</th>
                            <th>Original Tableau Formula</th>
                            <th>Dependencies</th>
                            <th>Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {artifacts.calculated_fields.slice(0, 50).map((cf: any, idx: number) => (
                            <tr key={idx}>
                              <td style={{ fontWeight: 600 }}>{cf.caption || cf.name}</td>
                              <td className={styles.formulaCell} title={cf.formula}>
                                {cf.formula}
                              </td>
                              <td style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                                {Array.isArray(cf.dependencies) && cf.dependencies.length > 0
                                  ? cf.dependencies.join(", ")
                                  : "None"}
                              </td>
                              <td>
                                <span
                                  className={
                                    cf.type === "LOD"
                                      ? styles.typeLod
                                      : cf.type === "TABLE_CALC"
                                      ? styles.typeTableCalc
                                      : styles.typeStandard
                                  }
                                >
                                  {cf.type || "STANDARD"}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* 4. SOURCE MAPPING STAGE (INLINE MAPPING WORKFLOW) */}
          {stage.stage_id === "SOURCE_MAPPING" && (
            <>
              <div className={styles.section}>
                <button className={styles.sectionHeader} onClick={() => toggleSection("mapping")}>
                  <span>Source Mapping & Unity Catalog Discovery</span>
                  {openSections.mapping !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </button>
                {openSections.mapping !== false && (
                  <div className={styles.sectionBody}>
                    <InlineMappingPanel jobUuid={jobUuid} onExecute={onExecute} />
                  </div>
                )}
              </div>

              {/* Data Model Joins / Relationships */}
              {Array.isArray(artifacts.detected_joins) && artifacts.detected_joins.length > 0 && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("relationships")}>
                    <span>Data Model Relationships ({artifacts.detected_joins.length})</span>
                    {openSections.relationships !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.relationships !== false && (
                    <div className={styles.sectionBody}>
                      <RelationshipDiagram joins={artifacts.detected_joins} />
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* 5. CALC LOGIC CONVERSION STAGE */}
          {stage.stage_id === "CALC_LOGIC_CONVERSION" && (
            <>
              {Array.isArray(artifacts.conversions) && artifacts.conversions.length > 0 && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("conversions")}>
                    <span>Transpiled SQL Expressions ({artifacts.conversions.length})</span>
                    {openSections.conversions !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.conversions !== false && (
                    <div className={styles.sectionBody}>
                      <table className={styles.formulaTable}>
                        <thead>
                          <tr>
                            <th>Field</th>
                            <th>Original Formula</th>
                            <th>Converted Databricks SQL</th>
                          </tr>
                        </thead>
                        <tbody>
                          {artifacts.conversions.slice(0, 50).map((c: any, idx: number) => (
                            <tr key={idx}>
                              <td style={{ fontWeight: 600 }}>{c.caption || c.name}</td>
                              <td className={styles.formulaCell} title={c.original_formula}>
                                {c.original_formula}
                              </td>
                              <td className={styles.sqlCell} title={c.compiled_sql}>
                                {c.compiled_sql || "-- Direct column pass-through"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {stage.generated_code && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("code")}>
                    <span>Generated SQL Script</span>
                    {openSections.code !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.code !== false && (
                    <div className={styles.sectionBody}>
                      <pre className={styles.codeBlock}>{stage.generated_code}</pre>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* 6. LAYOUT GENERATION STAGE */}
          {stage.stage_id === "LAYOUT_GENERATION" && (
            <>
              {Array.isArray(artifacts.pages) && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("pages")}>
                    <span>Lakeview Dashboard Pages ({artifacts.pages.length})</span>
                    {openSections.pages !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.pages !== false && (
                    <div className={styles.sectionBody}>
                      {artifacts.pages.map((page: any, idx: number) => (
                        <div key={idx} style={{ marginBottom: "1rem" }}>
                          <h4 style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                            Page: {page.display_name || page.name} ({page.widget_count} widgets)
                          </h4>
                          <div className={styles.widgetGrid}>
                            {Array.isArray(page.widgets) &&
                              page.widgets.map((w: any, wIdx: number) => (
                                <div key={wIdx} className={styles.widgetCard}>
                                  <div className={styles.widgetName}>{w.name || "Widget"}</div>
                                  <div className={styles.widgetMeta}>
                                    Type: {w.type || "Chart"} {w.visual_type ? `(${w.visual_type})` : ""}
                                  </div>
                                  <div className={styles.widgetMeta}>
                                    Grid: [{w.position?.x}, {w.position?.y}, {w.position?.w}x{w.position?.h}]
                                  </div>
                                </div>
                              ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* 7. SCHEMA VALIDATION STAGE */}
          {stage.stage_id === "SCHEMA_VALIDATION" && (
            <>
              {stage.generated_code && (
                <div className={styles.section}>
                  <button className={styles.sectionHeader} onClick={() => toggleSection("json")}>
                    <span>Generated Lakeview JSON Spec</span>
                    {openSections.json !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  {openSections.json !== false && (
                    <div className={styles.sectionBody}>
                      <pre className={styles.jsonViewer}>{stage.generated_code}</pre>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* 8. PUBLISH STAGE */}
          {stage.stage_id === "PUBLISH" && (
            <div className={styles.downloadCta}>
              <h3>Databricks Deployment Ready</h3>
              <p className={styles.downloadHint}>
                Publish the generated Lakeview JSON directly to your Databricks Workspace SQL Warehouse.
              </p>
            </div>
          )}

          {/* 9. FINALIZE STAGE */}
          {stage.stage_id === "FINALIZE" && (
            <div className={styles.downloadCta}>
              <button
                className={styles.downloadBtn}
                onClick={() => {
                  window.open(`/api/v1/migrations/${jobUuid}/json`, "_blank");
                }}
              >
                <Download size={18} /> Download Generated .lvdash.json
              </button>
              <div className={styles.downloadHint}>
                File ready for import into Databricks Lakeview Dashboards
              </div>
            </div>
          )}

          {/* ── Issues (Errors & Warnings) ── */}
          {(stage.errors.length > 0 || stage.warnings.length > 0) && (
            <div className={styles.section}>
              <button className={styles.sectionHeader} onClick={() => toggleSection("issues")}>
                <span>
                  Issues ({stage.errors.length} errors, {stage.warnings.length} warnings)
                </span>
                {openSections.issues !== false ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </button>
              {openSections.issues !== false && (
                <div className={styles.sectionBody}>
                  {stage.errors.map((err, idx) => (
                    <div key={`err-${idx}`} className={styles.issueError}>
                      <AlertTriangle size={14} style={{ display: "inline", marginRight: 6 }} />
                      {err}
                    </div>
                  ))}
                  {stage.warnings.map((warn, idx) => (
                    <div key={`warn-${idx}`} className={styles.issueWarn}>
                      <AlertTriangle size={14} style={{ display: "inline", marginRight: 6 }} />
                      {warn}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Logs Section ── */}
          {stage.logs.length > 0 && (
            <div className={styles.section}>
              <button className={styles.sectionHeader} onClick={() => toggleSection("logs")}>
                <span>Execution Logs ({stage.logs.length} lines)</span>
                {openSections.logs ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </button>
              {openSections.logs && (
                <div className={styles.sectionBody}>
                  <div className={styles.logBox}>
                    {stage.logs.map((logLine, idx) => {
                      let logClass = styles.logLine;
                      if (logLine.includes("[SUCCESS]")) logClass = `${styles.logLine} ${styles.logSuccess}`;
                      if (logLine.includes("[WARNING]") || logLine.includes("[WARN]"))
                        logClass = `${styles.logLine} ${styles.logWarn}`;
                      if (logLine.includes("[ERROR]") || logLine.includes("[FATAL]"))
                        logClass = `${styles.logLine} ${styles.logError}`;

                      return (
                        <div key={idx} className={logClass}>
                          {logLine}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
