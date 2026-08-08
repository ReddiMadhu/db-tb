/* ═══════════════════════════════════════════════
   Tableau to Databricks Migration — TypeScript Types
   ═══════════════════════════════════════════════ */

// ── Pipeline Stage Status ──
export type StageStatus = "WAITING" | "RUNNING" | "COMPLETED" | "WARNING" | "FAILED" | "SKIPPED";

// ── Stage Summary (from GET /stages) ──
export interface StageSummary {
  stage_id: string;
  stage_number: number;
  stage_name: string;
  status: StageStatus;
  duration_ms: number | null;
  metrics: Record<string, unknown>;
}

// ── Stage Detail (from GET /stages/{stageId}) ──
export interface StageDetail {
  stage_id: string;
  stage_number: number;
  stage_name: string;
  status: StageStatus;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  input_summary: string | null;
  output_summary: string | null;
  metrics: Record<string, unknown>;
  logs: string[];
  warnings: string[];
  errors: string[];
  generated_code: string | null;
  artifacts: Record<string, unknown>;
}

// ── Pipeline Progress (from GET /progress) ──
export interface PipelineProgress {
  job_uuid: string;
  job_status: string;
  overall_progress: number;
  current_stage_id: string | null;
  current_stage_number: number | null;
  current_activity: string | null;
  elapsed_ms: number;
  completed_stages: number;
  total_stages: number;
  stage_statuses: { stage_id: string; status: StageStatus; duration_ms: number | null }[];
  is_running: boolean;
  is_complete: boolean;
  is_failed: boolean;
}

// ── All Stages Response (from GET /stages) ──
export interface StagesResponse {
  job_uuid: string;
  stages: StageSummary[];
  overall_progress: number;
  current_stage: string | null;
  current_activity: string | null;
  stage_count: number;
}

// ── Job Status ──
export type JobStatus = "UPLOADED" | "PARSED" | "NEEDS_MAPPING" | "EXECUTING" | "COMPLETED" | "FAILED" | "DEPLOYED" | "NEEDS_REVIEW";

// ── Datasource Mapping Types ──
export interface TableauDatasourceInfo {
  name: string;
  caption: string;
  connection_type: string;
  tables: {
    name: string;
    raw_name: string;
    is_unresolved: boolean;
    clean_name: string;
  }[];
  column_count: number;
  worksheets: string[];
  is_databricks?: boolean;
  databricks_connection?: {
    host: string;
    http_path: string;
    catalog: string;
    schema: string;
    warehouse_id: string;
    auth_method: string;
    connection_class: string;
  };
}

export interface EmbeddedFileInfo {
  archive_path: string;
  filename: string;
  extension: string;
  size: number;
  uploadable: boolean;
  needs_conversion: boolean;
  is_hyper: boolean;
}

export interface MatchSuggestionItem {
  target_full_name: string;
  confidence_score: number;
  match_reason: string;
}

export interface DatasourceDiscoveryResponse {
  job_uuid: string;
  suggestions: Record<string, {
    datasource_name: string;
    connection_type: string;
    is_unresolved: boolean;
    matches: MatchSuggestionItem[];
    profile_match?: {
      target_full_name: string;
      profile_name: string;
    };
  }>;
  uc_table_count: number;
  tableau_table_count: number;
}

export interface DatasourceMappingItem {
  id?: number;
  tableau_datasource_name: string;
  tableau_table_name: string;
  tableau_connection_type: string;
  target_full_name: string;
  confidence_score?: number;
  status: "PENDING" | "MATCHED" | "CONFIRMED" | "FAILED" | "AUTO_DETECTED";
}

export interface CatalogItem {
  name: string;
  type: "catalog" | "schema" | "table";
  table_type?: string;
  full_name?: string;
  comment?: string;
}

export interface CatalogBrowseResponse {
  level: "catalogs" | "schemas" | "tables";
  catalog?: string;
  schema?: string;
  items: CatalogItem[];
}

export interface MappingValidationResponse {
  valid: boolean;
  errors: string[];
  mapped_count: number;
  total_count: number;
  mapping_status: "UNMAPPED" | "PARTIAL" | "COMPLETE";
  details: {
    tableau_table: string;
    target: string | null;
    exists: boolean;
    status: string;
  }[];
}

// ── Upload Response ──
export interface UploadResponse {
  status: string;
  job_uuid: string;
  filename: string;
  workbooks_found: number;
  datasources_count: number;
  worksheets_count: number;
  dashboards_count: number;
  parameters_count: number;
  actions_count: number;
  dependency_cycles: string[];
  orphan_fields_count: number;
  model_type: string;
  current_stage: number;
}

// ── Execute Response ──
export interface ExecuteResponse {
  status: string;
  job_uuid: string;
  validation_valid: boolean;
  validation_errors: string[];
  validation_warnings: string[];
  output_path: string;
}

// ── Status Response ──
export interface StatusResponse {
  job_uuid: string;
  status: JobStatus;
  current_stage: number;
  filename: string;
  created_at: string;
  completed_at: string | null;
  error_bag: ErrorBagItem[];
  has_output?: boolean;
  golden_override?: boolean;
  golden_source?: string | null;
}

export interface ErrorBagItem {
  level: string;
  message: string;
}

// ── Lakeview Dashboard ──
export interface LakeviewDashboard {
  datasets: LakeviewDataset[];
  pages: LakeviewPage[];
}

export interface LakeviewDataset {
  name: string;
  displayName: string;
  query: string;
}

export interface LakeviewPage {
  name: string;
  displayName: string;
  layout: LayoutItem[];
}

export interface LayoutItem {
  widget: LakeviewWidget;
  position: WidgetPosition;
}

export interface LakeviewWidget {
  name: string;
  queries?: WidgetQuery[];
  spec?: Record<string, unknown>;
  textbox_spec?: string;
}

export interface WidgetQuery {
  name: string;
  query: {
    datasetName: string;
    fields: { name: string; expression: string }[];
    disaggregated?: boolean;
  };
}

export interface WidgetPosition {
  x: number;
  y: number;
  width: number;
  height: number;
}

// ── Migration Report ──
export interface MigrationReport {
  source_file: string;
  tableau_version: string;
  model_type: string;
  total_worksheets: number;
  total_dashboards: number;
  total_datasources: number;
  total_expressions: number;
  expressions_compiled_rule: number;
  expressions_compiled_lod: number;
  expressions_compiled_table_calc: number;
  expressions_unsupported: number;
  lakeview_datasets: number;
  lakeview_pages: number;
  lakeview_widgets: number;
  validation_valid: boolean;
  validation_errors: string[];
  validation_warnings: string[];
}

// ── Bundle Response ──
export interface BundleResponse {
  databricks_yml: string;
  lvdash_json: Record<string, unknown>;
}

// ── Diff Response ──
export interface DiffResponse {
  diff: {
    datasets_added: unknown[];
    datasets_modified: unknown[];
    datasets_removed: string[];
    widgets_added: unknown[];
    widgets_modified: unknown[];
    widgets_removed: string[];
    has_changes: boolean;
  };
}

// ── Project (Local) ──
export interface Project {
  id: string;
  name: string;
  description: string;
  migrations: Migration[];
  createdAt: string;
}

export interface Migration {
  jobUuid: string;
  filename: string;
  status: JobStatus;
  currentStage: number;
  datasourcesCount: number;
  worksheetsCount: number;
  dashboardsCount: number;
  modelType: string;
  createdAt: string;
  completedAt: string | null;
}

// ── Validation ──
export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  tier_status: Record<string, boolean>;
}

// ── Databricks Connection ──
export interface DatabricksConnectionItem {
  id: number;
  name: string;
  host: string;
  token: string;
  token_full: string;
  warehouse_id: string | null;
  catalog: string | null;
  schema_name: string | null;
  is_default: boolean;
  has_token?: boolean;
  created_at: string | null;
}

// ── Business Insights & Lineage Types ──
export interface BusinessOverview {
  workbook_name?: string;
  dashboards_found?: number;
  worksheets_count?: number;
  visualizations_count?: number;
  datasources_count?: number;
  calculated_fields_count?: number;
  parameters_count?: number;
  filters_count?: number;
  estimated_success_pct?: string;
  migration_complexity?: string;
  estimated_processing_time?: string;
}

export interface FormulaConversionItem {
  name: string;
  caption?: string;
  formula_type?: string;
  original_formula: string;
  compiled_sql: string;
  ai_explanation?: string;
  confidence_score?: number;
  validation_status?: "VALID" | "WARNING" | "FAIL";
  datasource?: string;
  is_table_calc?: boolean;
}

export interface VisualCompatibilityItem {
  visual: string;
  status: "COMPATIBLE" | "UNSUPPORTED" | "CONVERTED";
  notes?: string;
}

export interface ColumnMappingLineageItem {
  source_column: string;
  detected_meaning: string;
  target_column: string;
  transformation: string;
  confidence: number;
}
