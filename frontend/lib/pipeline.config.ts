/* ═══════════════════════════════════════════════
   Tableau to Databricks Migration — Pipeline Configuration
   
   Single source of truth for all 9 pipeline stages.
   Edit this file to add/rename/reorder stages without UI changes.
   ═══════════════════════════════════════════════ */

import type { StageStatus } from "./types";

export interface StageDetailField {
  key: string;
  label: string;
  type: "text" | "number" | "code" | "list" | "badge" | "table" | "percentage";
  section: "metrics" | "details" | "logs" | "output";
}

export interface PipelineStageConfig {
  id: string;
  number: number;
  title: string;
  shortTitle: string;
  description: string;
  icon: string;
  backendStages: string[];
  detailFields: StageDetailField[];
  color: string;
}

export const PIPELINE_STAGES: PipelineStageConfig[] = [
  {
    id: "UPLOAD",
    number: 1,
    title: "Upload",
    shortTitle: "Upload",
    description: "Upload and validate Tableau workbook (.twbx / .twb)",
    icon: "Upload",
    backendStages: ["UPLOAD"],
    color: "var(--accent-info)",
    detailFields: [
      { key: "workbook_name", label: "Uploaded Workbook", type: "text", section: "metrics" },
      { key: "workbook_size", label: "Workbook Size", type: "text", section: "metrics" },
      { key: "sheets_detected", label: "Sheets Detected", type: "number", section: "metrics" },
      { key: "dashboard_count", label: "Dashboard Count", type: "number", section: "metrics" },
      { key: "datasource_count", label: "Datasource Count", type: "number", section: "metrics" },
      { key: "parameters_count", label: "Parameters", type: "number", section: "details" },
      { key: "tableau_version", label: "Detected Tableau Version", type: "text", section: "details" },
      { key: "model_type", label: "Model Type", type: "text", section: "details" },
      { key: "embedded_files_count", label: "Attached Assets", type: "number", section: "details" },
    ],
  },
  {
    id: "PARSE",
    number: 2,
    title: "Parse",
    shortTitle: "Parse",
    description: "Parse Tableau XML, extract object model, build DOM tree & dependency graph",
    icon: "FileSearch",
    backendStages: ["PARSE", "DAG"],
    color: "var(--accent-cyan)",
    detailFields: [
      { key: "worksheets_parsed", label: "Worksheets Parsed", type: "number", section: "metrics" },
      { key: "dashboards_parsed", label: "Dashboards Parsed", type: "number", section: "metrics" },
      { key: "datasource_count", label: "Datasources", type: "number", section: "metrics" },
      { key: "calculated_fields_detected", label: "Calculated Fields", type: "number", section: "metrics" },
      { key: "lod_expressions", label: "LOD Expressions", type: "number", section: "details" },
      { key: "parameters", label: "Parameters", type: "number", section: "details" },
      { key: "filters", label: "Filters", type: "number", section: "details" },
      { key: "custom_sql", label: "Custom SQL", type: "number", section: "details" },
      { key: "model_type", label: "Model Type", type: "text", section: "details" },
      { key: "tableau_version", label: "Tableau Version", type: "text", section: "details" },
      { key: "dependency_cycles", label: "Dependency Cycles", type: "list", section: "details" },
    ],
  },
  {
    id: "CALC_DEEP_DIVE",
    number: 3,
    title: "Calculation Deep Dive",
    shortTitle: "Calc Dive",
    description: "Analyze calculated fields, LOD expressions, window functions, and dependencies",
    icon: "Calculator",
    backendStages: ["EXPRESSIONS"],
    color: "var(--accent-purple)",
    detailFields: [
      { key: "calculated_fields", label: "Calculated Fields", type: "number", section: "metrics" },
      { key: "lod_expressions", label: "LOD Expressions", type: "number", section: "metrics" },
      { key: "window_functions", label: "Window Functions", type: "number", section: "metrics" },
      { key: "nested_calculations", label: "Nested Calculations", type: "number", section: "metrics" },
      { key: "table_calculations", label: "Table Calculations", type: "number", section: "details" },
      { key: "excluded_fields", label: "Excluded Fields", type: "number", section: "details" },
      { key: "complexity_analysis", label: "Complexity", type: "badge", section: "details" },
      { key: "migration_confidence", label: "Migration Confidence", type: "percentage", section: "details" },
      { key: "schema_mismatches", label: "Schema Mismatches", type: "number", section: "details" },
    ],
  },
  {
    id: "SOURCE_MAPPING",
    number: 4,
    title: "Source Mapping Validation",
    shortTitle: "Mapping",
    description: "Map Tableau datasources to Unity Catalog tables in Databricks",
    icon: "GitBranch",
    backendStages: ["MAPPING"],
    color: "var(--accent-amber)",
    detailFields: [
      { key: "total_tables", label: "Total Tables", type: "number", section: "metrics" },
      { key: "mapped_tables", label: "Mapped Tables", type: "number", section: "metrics" },
      { key: "unresolved_tables", label: "Unresolved Tables", type: "number", section: "metrics" },
      { key: "datasource_count", label: "Datasources", type: "number", section: "metrics" },
      { key: "connection_types", label: "Connection Types", type: "list", section: "details" },
      { key: "default_catalog", label: "Default Catalog", type: "text", section: "details" },
      { key: "default_schema", label: "Default Schema", type: "text", section: "details" },
      { key: "validation_status", label: "Validation Status", type: "badge", section: "details" },
    ],
  },
  {
    id: "CALC_LOGIC_CONVERSION",
    number: 5,
    title: "Calculation Logic Conversion",
    shortTitle: "SQL Conv.",
    description: "Convert Tableau formulas to Databricks-compatible Spark SQL",
    icon: "Code",
    backendStages: ["SQL"],
    color: "var(--accent-orange)",
    detailFields: [
      { key: "expressions_compiled", label: "Expressions Compiled", type: "number", section: "metrics" },
      { key: "expressions_unsupported", label: "Unsupported", type: "number", section: "metrics" },
      { key: "total_expressions", label: "Total Expressions", type: "number", section: "metrics" },
      { key: "compilation_rate", label: "Compilation Rate", type: "text", section: "metrics" },
      { key: "databricks_compatibility", label: "Databricks Compatibility", type: "badge", section: "details" },
    ],
  },
  {
    id: "LAYOUT_GENERATION",
    number: 6,
    title: "Dashboard Layout Generation",
    shortTitle: "Layout",
    description: "Generate Lakeview dashboard layout, widgets, and dataset specs",
    icon: "LayoutDashboard",
    backendStages: ["UBIM", "GENERATE"],
    color: "var(--accent-green)",
    detailFields: [
      { key: "pages_generated", label: "Pages Generated", type: "number", section: "metrics" },
      { key: "widgets_generated", label: "Widgets Generated", type: "number", section: "metrics" },
      { key: "datasets_generated", label: "Datasets Generated", type: "number", section: "metrics" },
      { key: "layout_grid", label: "Layout Grid", type: "text", section: "details" },
      { key: "visual_types_detected", label: "Visual Types", type: "list", section: "details" },
    ],
  },
  {
    id: "SCHEMA_VALIDATION",
    number: 7,
    title: "Lakeview Schema Validation",
    shortTitle: "Validate",
    description: "Validate generated JSON against Lakeview dashboard schema",
    icon: "ShieldCheck",
    backendStages: ["VALIDATE"],
    color: "var(--accent-info)",
    detailFields: [
      { key: "is_valid", label: "Valid", type: "badge", section: "metrics" },
      { key: "error_count", label: "Errors", type: "number", section: "metrics" },
      { key: "warning_count", label: "Warnings", type: "number", section: "metrics" },
      { key: "pruned_widgets", label: "Pruned Widgets", type: "number", section: "metrics" },
      { key: "tier_status", label: "Validation Tiers", type: "table", section: "details" },
    ],
  },
  {
    id: "PUBLISH",
    number: 8,
    title: "Publish to Databricks",
    shortTitle: "Publish",
    description: "Deploy dashboard to Databricks workspace via REST API",
    icon: "Rocket",
    backendStages: ["DEPLOY"],
    color: "var(--accent-green)",
    detailFields: [
      { key: "workspace", label: "Workspace", type: "text", section: "metrics" },
      { key: "warehouse_id", label: "Warehouse ID", type: "text", section: "metrics" },
      { key: "publish_status", label: "Publish Status", type: "badge", section: "metrics" },
      { key: "dashboard_url", label: "Dashboard URL", type: "text", section: "details" },
      { key: "dashboard_id", label: "Dashboard ID", type: "text", section: "details" },
    ],
  },
  {
    id: "FINALIZE",
    number: 9,
    title: "Finalize",
    shortTitle: "Finalize",
    description: "Generate migration package, reports, and download artifacts",
    icon: "PackageCheck",
    backendStages: ["REPORT"],
    color: "var(--accent-cyan)",
    detailFields: [
      { key: "worksheets_total", label: "Worksheets Total", type: "number", section: "metrics" },
      { key: "expressions_total", label: "Expressions Total", type: "number", section: "metrics" },
      { key: "expressions_compiled", label: "Compiled", type: "number", section: "metrics" },
      { key: "validation_valid", label: "Validation Passed", type: "badge", section: "metrics" },
      { key: "lakeview_pages", label: "Lakeview Pages", type: "number", section: "details" },
      { key: "lakeview_widgets", label: "Lakeview Widgets", type: "number", section: "details" },
      { key: "expressions_unsupported", label: "Unsupported Expressions", type: "number", section: "details" },
    ],
  },
];

export const PIPELINE_STAGE_COUNT = PIPELINE_STAGES.length;

// Helper: get stage config by ID
export function getStageConfig(stageId: string): PipelineStageConfig | undefined {
  return PIPELINE_STAGES.find((s) => s.id === stageId);
}

// Helper: get status color
export function getStatusColor(status: StageStatus): string {
  switch (status) {
    case "COMPLETED": return "var(--accent-green)";
    case "RUNNING": return "var(--accent-orange)";
    case "WARNING": return "var(--accent-amber)";
    case "FAILED": return "var(--accent-red)";
    case "SKIPPED": return "var(--text-disabled)";
    case "WAITING":
    default: return "var(--text-tertiary)";
  }
}

// Helper: get status label
export function getStatusLabel(status: StageStatus): string {
  switch (status) {
    case "COMPLETED": return "Completed";
    case "RUNNING": return "Running";
    case "WARNING": return "Warning";
    case "FAILED": return "Failed";
    case "SKIPPED": return "Skipped";
    case "WAITING":
    default: return "Waiting";
  }
}
