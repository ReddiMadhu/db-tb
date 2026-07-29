/* ═══════════════════════════════════════════════
   LakeShift TypeScript Types
   ═══════════════════════════════════════════════ */

// ── Pipeline Stages ──
export type PipelineStage =
  | "UPLOAD"
  | "PARSE"
  | "DAG"
  | "EXPRESSIONS"
  | "SQL"
  | "UBIM"
  | "GENERATE"
  | "VALIDATE"
  | "DEPLOY"
  | "REPORT";

export const PIPELINE_STAGES: { key: PipelineStage; label: string; number: number }[] = [
  { key: "UPLOAD", label: "Upload", number: 1 },
  { key: "PARSE", label: "Parse", number: 2 },
  { key: "DAG", label: "DAG", number: 3 },
  { key: "EXPRESSIONS", label: "Expressions", number: 4 },
  { key: "SQL", label: "SQL", number: 5 },
  { key: "UBIM", label: "UBIM", number: 6 },
  { key: "GENERATE", label: "Generate", number: 7 },
  { key: "VALIDATE", label: "Validate", number: 8 },
  { key: "DEPLOY", label: "Deploy", number: 9 },
  { key: "REPORT", label: "Report", number: 10 },
];

// ── Job Status ──
export type JobStatus = "UPLOADED" | "PARSED" | "EXECUTING" | "COMPLETED" | "FAILED" | "DEPLOYED" | "NEEDS_REVIEW";

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
