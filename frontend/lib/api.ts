/* ═══════════════════════════════════════════════
   Tableau to Databricks Migration — API Client
   ═══════════════════════════════════════════════ */

import type {
  UploadResponse,
  ExecuteResponse,
  StatusResponse,
  LakeviewDashboard,
  MigrationReport,
  BundleResponse,
  DiffResponse,
  StagesResponse,
  StageDetail,
  PipelineProgress,
  DatabricksConnectionItem,
} from "./types";

// Base URL — configurable for Azure App Service deployment
const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error: ${res.status}`);
  }
  return res.json();
}

// ── List Jobs ──
export async function listMigrationJobs(): Promise<Array<{
  id: number;
  job_uuid: string;
  source_filename: string;
  status: string;
  current_stage: number;
  created_at: string | null;
  completed_at: string | null;
}>> {
  return apiFetch("/migrations/");
}

// ── Upload ──
export async function uploadWorkbook(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/migrations/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

// ── Execute Pipeline ──
export async function executePipeline(jobUuid: string): Promise<ExecuteResponse> {
  return apiFetch<ExecuteResponse>(`/migrations/${jobUuid}/execute?sync=false`, {
    method: "POST",
  });
}

// ── Get Status ──
export async function getMigrationStatus(jobUuid: string): Promise<StatusResponse> {
  return apiFetch<StatusResponse>(`/migrations/${jobUuid}/status`);
}

// ── Get Lakeview JSON ──
export async function getLakeviewJson(jobUuid: string): Promise<LakeviewDashboard> {
  return apiFetch<LakeviewDashboard>(`/migrations/${jobUuid}/json`);
}

// ── Get Report ──
export async function getMigrationReport(jobUuid: string): Promise<MigrationReport> {
  return apiFetch<MigrationReport>(`/migrations/${jobUuid}/report`);
}

// ── Get Bundle ──
export async function getBundle(jobUuid: string): Promise<BundleResponse> {
  return apiFetch<BundleResponse>(`/migrations/${jobUuid}/bundle`);
}

// ── Get Diff ──
export async function getDiff(jobUuid: string): Promise<DiffResponse> {
  return apiFetch<DiffResponse>(`/migrations/${jobUuid}/diff`);
}

// ── Deploy ──
export async function deployToDatabricks(
  jobUuid: string,
  warehouseId: string,
  host: string,
  token: string
): Promise<unknown> {
  return apiFetch(`/migrations/${jobUuid}/deploy`, {
    method: "POST",
    body: JSON.stringify({ warehouse_id: warehouseId, host, token }),
  });
}

// ═══════════════════════════════════════════════
// NEW — Pipeline Stage APIs
// ═══════════════════════════════════════════════

// ── Get All Stages ──
export async function getStages(jobUuid: string): Promise<StagesResponse> {
  return apiFetch<StagesResponse>(`/migrations/${jobUuid}/stages`);
}

// ── Get Stage Detail ──
export async function getStageDetail(jobUuid: string, stageId: string): Promise<StageDetail> {
  return apiFetch<StageDetail>(`/migrations/${jobUuid}/stages/${stageId}`);
}

// ── Get Progress (polling) ──
export async function getProgress(jobUuid: string): Promise<PipelineProgress> {
  return apiFetch<PipelineProgress>(`/migrations/${jobUuid}/progress`);
}

// ═══════════════════════════════════════════════
// NEW — Connections APIs
// ═══════════════════════════════════════════════

// ── List Connections ──
export async function listConnections(): Promise<DatabricksConnectionItem[]> {
  return apiFetch<DatabricksConnectionItem[]>("/connections/");
}

// ── Save Connection ──
export async function saveConnection(data: {
  name: string;
  host: string;
  token: string;
  warehouse_id?: string;
  catalog?: string;
  schema_name?: string;
  is_default?: boolean;
}): Promise<{ id: number; name: string; host: string; message: string }> {
  return apiFetch("/connections/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Delete Connection ──
export async function deleteConnection(id: number): Promise<{ message: string }> {
  return apiFetch(`/connections/${id}`, { method: "DELETE" });
}

// ── Get Default Connection ──
export async function getDefaultConnection(): Promise<{
  has_default: boolean;
  connection: DatabricksConnectionItem | null;
}> {
  return apiFetch("/connections/default");
}

// ═══════════════════════════════════════════════
// Datasource Mapping APIs (unchanged)
// ═══════════════════════════════════════════════

import type {
  TableauDatasourceInfo,
  EmbeddedFileInfo,
  DatasourceDiscoveryResponse,
  DatasourceMappingItem,
  CatalogBrowseResponse,
  MappingValidationResponse,
} from "./types";

export async function getJobDatasources(jobUuid: string): Promise<{
  job_uuid: string;
  datasources: TableauDatasourceInfo[];
  embedded_files: EmbeddedFileInfo[];
  existing_mappings: Record<string, { target_full_name: string; status: string; confidence_score?: number }>;
  mapping_status: string;
}> {
  return apiFetch(`/mapping/${jobUuid}/datasources`);
}

export async function discoverMappings(
  jobUuid: string,
  host: string,
  token: string,
  warehouseId: string
): Promise<DatasourceDiscoveryResponse> {
  return apiFetch(`/mapping/${jobUuid}/datasources/discover`, {
    method: "POST",
    body: JSON.stringify({ host, token, warehouse_id: warehouseId }),
  });
}

export async function autoUploadEmbedded(
  jobUuid: string,
  host: string,
  token: string,
  warehouseId: string,
  catalog: string,
  schemaName: string
): Promise<{
  job_uuid: string;
  results: { table_name: string; full_name: string; source_file: string; status: string; error?: string }[];
  uploaded_count: number;
  failed_count: number;
}> {
  return apiFetch(`/mapping/${jobUuid}/datasources/auto-upload`, {
    method: "POST",
    body: JSON.stringify({ host, token, warehouse_id: warehouseId, catalog, schema_name: schemaName }),
  });
}

export async function browseCatalog(
  host: string,
  token: string,
  warehouseId?: string,
  catalog?: string,
  schemaName?: string
): Promise<CatalogBrowseResponse> {
  const params = new URLSearchParams({ host, token });
  if (warehouseId) params.append("warehouse_id", warehouseId);
  if (catalog) params.append("catalog", catalog);
  if (schemaName) params.append("schema_name", schemaName);
  return apiFetch(`/mapping/catalog/browse?${params.toString()}`);
}

export async function searchCatalog(
  host: string,
  token: string,
  query: string,
  warehouseId?: string
): Promise<{ query: string; results: { catalog: string; schema: string; table: string; full_name: string; table_type: string }[]; count: number }> {
  const params = new URLSearchParams({ host, token, q: query });
  if (warehouseId) params.append("warehouse_id", warehouseId);
  return apiFetch(`/mapping/catalog/search?${params.toString()}`);
}

export async function saveMappings(
  jobUuid: string,
  mappings: DatasourceMappingItem[]
): Promise<{ job_uuid: string; saved_count: number; confirmed_count: number; mapping_status: string }> {
  return apiFetch(`/mapping/${jobUuid}/mapping`, {
    method: "POST",
    body: JSON.stringify({ mappings }),
  });
}

export async function getSavedMappings(jobUuid: string): Promise<{
  job_uuid: string;
  mapping_status: string;
  mappings: DatasourceMappingItem[];
}> {
  return apiFetch(`/mapping/${jobUuid}/mapping`);
}

export async function validateMappings(
  jobUuid: string,
  host: string,
  token: string,
  warehouseId?: string
): Promise<MappingValidationResponse> {
  return apiFetch(`/mapping/${jobUuid}/mapping/validate`, {
    method: "POST",
    body: JSON.stringify({ host, token, warehouse_id: warehouseId }),
  });
}
