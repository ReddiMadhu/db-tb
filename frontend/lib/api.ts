/* ═══════════════════════════════════════════════
   LakeShift API Client
   ═══════════════════════════════════════════════ */

import type {
  UploadResponse,
  ExecuteResponse,
  StatusResponse,
  LakeviewDashboard,
  MigrationReport,
  BundleResponse,
  DiffResponse,
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
  return apiFetch<ExecuteResponse>(`/migrations/${jobUuid}/execute`, {
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
