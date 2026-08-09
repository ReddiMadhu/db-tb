"use client";

import React, { useState, useMemo, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import {
  ShieldCheck,
  Code2,
  GitCompare,
  FolderTree,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Copy,
  Download,
  RotateCcw,
  Sparkles,
  Rocket,
  ArrowRight,
  ExternalLink,
  FileCheck,
  Layers,
  Database,
  LayoutGrid,
  PieChart,
  BarChart3,
  Server,
  Key,
  Check,
  X,
  FileText,
} from "lucide-react";
import type { StageDetail } from "@/lib/types";
import { getLakeviewJson, getDefaultConnection, deployToDatabricks } from "@/lib/api";
import styles from "./DeploymentReviewDetail.module.css";

// Dynamically import Monaco Editor to avoid SSR hydration issues
const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div style={{ padding: "2rem", color: "#888888", textAlign: "center" }}>
      Loading VS Code Monaco Editor...
    </div>
  ),
});

interface DeploymentReviewDetailProps {
  jobUuid: string;
  stage: StageDetail;
  onSelectNextStage?: (stageId: string) => void;
  goldenOverride?: boolean;
}

export default function DeploymentReviewDetail({
  jobUuid,
  stage,
  onSelectNextStage,
  goldenOverride = false,
}: DeploymentReviewDetailProps) {
  const artifacts = (stage?.artifacts || {}) as Record<string, any>;
  const metrics = (stage?.metrics || {}) as Record<string, any>;

  // Seed Monaco from stage preview even in golden mode (already backfilled to
  // curated JSON). Refresh from /json when available; never wipe to empty on failure.
  const rawJsonFromStage = useMemo(() => {
    const raw = stage?.generated_code || artifacts?.generated_json_preview;
    if (raw && typeof raw === "string" && raw.trim().startsWith("{")) {
      try {
        const parsed = JSON.parse(raw);
        return JSON.stringify(parsed, null, 2);
      } catch {
        return raw;
      }
    }
    if (raw && typeof raw === "object") {
      return JSON.stringify(raw, null, 2);
    }
    return "";
  }, [stage, artifacts]);

  const [jsonCode, setJsonCode] = useState<string>(rawJsonFromStage);
  const [originalJsonStr, setOriginalJsonStr] = useState<string>(rawJsonFromStage);
  const [fetchingJson, setFetchingJson] = useState<boolean>(!rawJsonFromStage || goldenOverride);
  const [connectionResolved, setConnectionResolved] = useState(false);

  // Active Connection Info
  const [connectionInfo, setConnectionInfo] = useState<{
    host: string;
    warehouse_id: string;
    catalog: string;
    schema_name: string;
  }>({
    host: artifacts.workspace || "",
    warehouse_id: artifacts.warehouse_id || "",
    // Never invent a catalog/schema — empty means the deploy call omits
    // dataset_catalog/dataset_schema and lets FQN SQL stand alone.
    catalog: artifacts.catalog || "",
    schema_name: artifacts.schema_name || "",
  });
  // True when the saved default connection (or its response) has a PAT.
  // When true, deploy lets the server resolve the token — no paste prompt.
  const [hasSavedToken, setHasSavedToken] = useState(false);

  // Fetch official JSON (always when golden or stage preview missing)
  useEffect(() => {
    if (!jobUuid) return;
    if (!goldenOverride && jsonCode) return;

    setFetchingJson(true);
    getLakeviewJson(jobUuid)
      .then((data) => {
        const str = JSON.stringify(data, null, 2);
        setJsonCode(str);
        setOriginalJsonStr(str);
      })
      .catch(() => {
        // Keep stage-seeded JSON if present; do not clear to empty on failure.
        if (rawJsonFromStage) {
          setJsonCode(rawJsonFromStage);
          setOriginalJsonStr(rawJsonFromStage);
          return;
        }
        if (goldenOverride) {
          return;
        }
        const dynSpec = {
          pages: artifacts.pages || [
            {
              name: "page_1",
              displayName: artifacts.dashboard_title || "Databricks Lakeview Dashboard",
              layout: artifacts.widgets || [],
            },
          ],
          widgets: artifacts.widgets || [],
          datasets: artifacts.datasets || [],
        };
        const str = JSON.stringify(dynSpec, null, 2);
        setJsonCode(str);
        setOriginalJsonStr(str);
      })
      .finally(() => setFetchingJson(false));
  }, [jobUuid, goldenOverride]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch active Databricks connection details dynamically
  useEffect(() => {
    getDefaultConnection()
      .then((res) => {
        const hasTok = Boolean(
          res.has_token || res.connection?.has_token || res.connection?.token
        );
        setHasSavedToken(hasTok);
        if (res.has_default && res.connection) {
          setConnectionInfo({
            host: res.connection.host || "",
            warehouse_id: res.connection.warehouse_id || "",
            catalog: res.connection.catalog || "",
            schema_name: res.connection.schema_name || "",
          });
        }
      })
      .catch(() => {})
      .finally(() => setConnectionResolved(true));
  }, []);

  const [viewMode, setViewMode] = useState<"code" | "tree" | "diff">("code");
  const editorRef = useRef<any>(null);

  // Publish Modal state
  const [isPublishing, setIsPublishing] = useState<boolean>(false);
  const [showPublishModal, setShowPublishModal] = useState<boolean>(false);
  const [publishStep, setPublishStep] = useState<number>(0);
  const [publishComplete, setPublishComplete] = useState<boolean>(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [publishWarning, setPublishWarning] = useState<string | null>(null);
  const [patTokenInput, setPatTokenInput] = useState<string>("");
  const [hostOverrideInput, setHostOverrideInput] = useState<string>("");
  const [warehouseOverrideInput, setWarehouseOverrideInput] = useState<string>("");
  const [publishedDashboardUrl, setPublishedDashboardUrl] = useState<string | null>(
    artifacts.published_url || null
  );
  const [needsCredentials, setNeedsCredentials] = useState(false);

  const PLACEHOLDER_HOSTS = new Set([
    "",
    "workspace",
    "databricks workspace",
    "https://xxx.cloud.databricks.com",
  ]);
  const PLACEHOLDER_WAREHOUSES = new Set([
    "",
    "warehouse",
    "sql warehouse",
    "serverless",
    "serverless warehouse",
  ]);

  const isPlaceholderHost = (raw: string) => {
    const v = raw.trim().toLowerCase();
    return PLACEHOLDER_HOSTS.has(v);
  };

  const isPlaceholderWarehouse = (raw: string) => {
    const v = raw.trim().toLowerCase();
    return PLACEHOLDER_WAREHOUSES.has(v);
  };

  const errorNeedsCredentials = (msg: string) => {
    const m = msg.toLowerCase();
    return (
      m.includes("credential") ||
      m.includes("host url") ||
      m.includes("databricks host") ||
      m.includes("personal access token") ||
      m.includes("(pat)") ||
      m.includes("pat token") ||
      m.includes("databricks_token") ||
      m.includes("databricks_host") ||
      m.includes("warehouse id") ||
      m.includes("warehouse_id") ||
      m.includes("default_warehouse") ||
      /\b401\b/.test(m) ||
      /\b403\b/.test(m) ||
      m.includes("unauthorized") ||
      m.includes("forbidden")
    );
  };

  const closePublishModal = () => {
    if (isPublishing) return;
    setShowPublishModal(false);
    setPublishError(null);
    setPublishWarning(null);
    setPublishComplete(false);
    setPublishStep(0);
    setNeedsCredentials(false);
  };

  // Parsed JSON Object & Dynamic Object Counts
  const parsedJsonObject = useMemo(() => {
    try {
      return JSON.parse(jsonCode);
    } catch {
      return null;
    }
  }, [jsonCode]);

  const objectCounts = useMemo(() => {
    if (!parsedJsonObject) {
      return {
        dashboards: 1,
        pages: metrics.pages_generated ?? 0,
        widgets: metrics.widgets_generated ?? 0,
        queries: metrics.datasets_generated ?? 0,
        datasets: metrics.datasets_generated ?? 0,
      };
    }

    const pages = Array.isArray(parsedJsonObject.pages) ? parsedJsonObject.pages.length : 0;
    const widgets = Array.isArray(parsedJsonObject.widgets)
      ? parsedJsonObject.widgets.length
      : parsedJsonObject.pages?.reduce((acc: number, p: any) => acc + (p.layout?.length || 0), 0) || 0;
    const datasets = Array.isArray(parsedJsonObject.datasets) ? parsedJsonObject.datasets.length : 0;

    return {
      dashboards: 1,
      pages: pages || metrics.pages_generated || 1,
      widgets: widgets || metrics.widgets_generated || 0,
      queries: datasets || metrics.datasets_generated || 0,
      datasets: datasets || metrics.datasets_generated || 0,
    };
  }, [parsedJsonObject, metrics]);

  // Live validation calculations
  const validationResult = useMemo(() => {
    const issues: Array<{
      type: "error" | "warning" | "suggestion";
      line: number;
      message: string;
    }> = [];

    // Backend validation errors/warnings if available
    if (Array.isArray(artifacts.validation_errors)) {
      artifacts.validation_errors.forEach((err: string, idx: number) => {
        issues.push({ type: "error", line: idx + 1, message: err });
      });
    }
    if (Array.isArray(artifacts.validation_warnings)) {
      artifacts.validation_warnings.forEach((warn: string, idx: number) => {
        issues.push({ type: "warning", line: idx + 2, message: warn });
      });
    }

    if (jsonCode) {
      try {
        const parsed = JSON.parse(jsonCode);
        if (!parsed.pages) {
          issues.push({
            type: "error",
            line: 1,
            message: "Missing required root property 'pages'.",
          });
        } else if (!Array.isArray(parsed.pages)) {
          issues.push({
            type: "error",
            line: 2,
            message: "Property 'pages' must be an array.",
          });
        }

        if (parsed.widgets && Array.isArray(parsed.widgets)) {
          parsed.widgets.forEach((w: any, index: number) => {
            if (!w.name) {
              issues.push({
                type: "error",
                line: index * 6 + 5,
                message: `Widget at index ${index} is missing 'name' attribute.`,
              });
            }
            if (w.widgetNamee) {
              issues.push({
                type: "error",
                line: index * 6 + 6,
                message: `Unexpected property 'widgetNamee'. Did you mean 'widgetName'?`,
              });
            }
          });
        }
      } catch (err: any) {
        issues.push({
          type: "error",
          line: 1,
          message: `JSON Syntax Error: ${err.message}`,
        });
      }
    }

    const errors = issues.filter((i) => i.type === "error");
    const warnings = issues.filter((i) => i.type === "warning");
    const suggestions = issues.filter((i) => i.type === "suggestion");

    return {
      isValid: errors.length === 0,
      errors,
      warnings,
      suggestions,
    };
  }, [jsonCode, artifacts]);

  // Format JSON handler
  const handleFormatJson = () => {
    try {
      const parsed = JSON.parse(jsonCode);
      setJsonCode(JSON.stringify(parsed, null, 2));
    } catch (e) {
      alert("Cannot format: Invalid JSON syntax.");
    }
  };

  // Reset JSON handler
  const handleReset = () => {
    if (confirm("Reset JSON to original generated Lakeview specification?")) {
      setJsonCode(originalJsonStr);
    }
  };

  // Copy JSON handler
  const handleCopy = () => {
    navigator.clipboard.writeText(jsonCode);
    alert("Lakeview JSON copied to clipboard!");
  };

  // Download JSON handler
  const handleDownloadJson = () => {
    const blob = new Blob([jsonCode], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `lakeview_dashboard_${jobUuid.slice(0, 8)}.lvdash.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Jump to line in Monaco
  const handleJumpToLine = (line: number) => {
    setViewMode("code");
    if (editorRef.current) {
      editorRef.current.revealLineInCenter(line);
      editorRef.current.setPosition({ lineNumber: line, column: 1 });
      editorRef.current.focus();
    }
  };

  // Handle Publish flow to Databricks API
  const handleStartPublish = async () => {
    setShowPublishModal(true);
    setPublishComplete(false);
    setPublishWarning(null);
    setNeedsCredentials(false);

    if (!validationResult.isValid) {
      setIsPublishing(false);
      setPublishStep(0);
      setPublishError(
        "Schema validation failed. Fix JSON errors in the editor before publishing to Databricks."
      );
      return;
    }

    setIsPublishing(true);
    setPublishStep(1);
    setPublishError(null);

    try {
      setPublishStep(2);

      // Always refresh default connection; backend still falls back to .env
      let latestConn = { ...connectionInfo };
      try {
        const res = await getDefaultConnection();
        const hasTok = Boolean(
          res.has_token || res.connection?.has_token || res.connection?.token
        );
        setHasSavedToken(hasTok);
        if (res.has_default && res.connection) {
          latestConn = {
            host: res.connection.host || latestConn.host || "",
            warehouse_id: res.connection.warehouse_id || latestConn.warehouse_id || "",
            catalog: res.connection.catalog || latestConn.catalog || "",
            schema_name: res.connection.schema_name || latestConn.schema_name || "",
          };
          setConnectionInfo(latestConn);
          // Prefill override fields only if empty so Retry can edit them when needed
          if (!hostOverrideInput.trim() && latestConn.host) {
            setHostOverrideInput(latestConn.host);
          }
          if (!warehouseOverrideInput.trim() && latestConn.warehouse_id) {
            setWarehouseOverrideInput(latestConn.warehouse_id);
          }
        }
        setConnectionResolved(true);
      } catch {
        /* server .env / settings may still resolve credentials */
      }

      // Manual overrides from the retry panel take precedence when non-placeholder
      const hostOverride = (hostOverrideInput || "").trim();
      const warehouseOverride = (warehouseOverrideInput || "").trim();
      if (hostOverride && !isPlaceholderHost(hostOverride)) {
        latestConn = { ...latestConn, host: hostOverride };
      }
      if (warehouseOverride && !isPlaceholderWarehouse(warehouseOverride)) {
        latestConn = { ...latestConn, warehouse_id: warehouseOverride };
      }

      const whRaw = (latestConn.warehouse_id || "").trim();
      const whId = whRaw && !isPlaceholderWarehouse(whRaw) ? whRaw : undefined;

      const hostRaw = (latestConn.host || "").trim();
      const hostUrl = hostRaw && !isPlaceholderHost(hostRaw) ? hostRaw : undefined;

      const tokenOverride = (patTokenInput || "").trim() || undefined;

      if (!jsonCode || !jsonCode.trim().startsWith("{")) {
        setIsPublishing(false);
        setPublishStep(0);
        setPublishError(
          "Lakeview JSON is empty in the editor. Wait for the dashboard JSON to load, then try again."
        );
        return;
      }

      setPublishStep(3);
      // Empty {} is fine — server resolves Connection → .env
      const deployBody: {
        warehouse_id?: string;
        host?: string;
        token?: string;
        catalog?: string;
        schema_name?: string;
      } = {};
      if (whId) deployBody.warehouse_id = whId;
      if (hostUrl) deployBody.host = hostUrl;
      if (tokenOverride) deployBody.token = tokenOverride;
      if (latestConn.catalog) deployBody.catalog = latestConn.catalog;
      if (latestConn.schema_name) deployBody.schema_name = latestConn.schema_name;

      const res = await deployToDatabricks(jobUuid, deployBody);

      setPublishStep(4);
      setPublishStep(5);
      setPublishComplete(true);
      setIsPublishing(false);
      setNeedsCredentials(false);
      if (res.published_url) {
        setPublishedDashboardUrl(res.published_url);
      }
      if (res.publish_warning) {
        setPublishWarning(res.publish_warning);
      }
    } catch (err: any) {
      const msg =
        err.message ||
        "Databricks deployment failed. Please verify your host URL, warehouse ID, and PAT token.";
      setIsPublishing(false);
      setPublishStep(0);
      setPublishError(msg);
      setNeedsCredentials(errorNeedsCredentials(msg));
    }
  };

  // Dynamic Diff computation
  const diffLines = useMemo(() => {
    const origLines = originalJsonStr.split("\n");
    const modLines = jsonCode.split("\n");
    const maxLen = Math.max(origLines.length, modLines.length);
    const result = [];

    for (let i = 0; i < maxLen; i++) {
      const orig = origLines[i];
      const mod = modLines[i];

      if (orig === mod) {
        result.push({ type: "same", lineNum: i + 1, content: mod || "" });
      } else if (orig !== undefined && mod !== undefined) {
        result.push({ type: "modified", lineNum: i + 1, content: mod });
      } else if (orig === undefined) {
        result.push({ type: "added", lineNum: i + 1, content: mod });
      } else {
        result.push({ type: "deleted", lineNum: i + 1, content: orig });
      }
    }
    return result;
  }, [originalJsonStr, jsonCode]);

  return (
    <div className={styles.container}>

      {/* ── View Controls & Action Toolbar ── */}
      <div className={styles.controlsBar}>
        <div className={styles.viewModeGroup}>
          <button
            className={`${styles.viewBtn} ${viewMode === "code" ? styles.activeViewBtn : ""}`}
            onClick={() => setViewMode("code")}
          >
            <Code2 size={15} /> Code View (Monaco)
          </button>
          <button
            className={`${styles.viewBtn} ${viewMode === "tree" ? styles.activeViewBtn : ""}`}
            onClick={() => setViewMode("tree")}
          >
            <FolderTree size={15} /> Tree View
          </button>
          <button
            className={`${styles.viewBtn} ${viewMode === "diff" ? styles.activeViewBtn : ""}`}
            onClick={() => setViewMode("diff")}
          >
            <GitCompare size={15} /> Difference Viewer
          </button>
        </div>

        <div className={styles.actionGroup}>
          <button className={styles.secondaryBtn} onClick={handleReset} title="Reset to original JSON">
            <RotateCcw size={14} /> Reset
          </button>
          <button className={styles.secondaryBtn} onClick={handleCopy}>
            <Copy size={14} /> Copy
          </button>
          <button className={styles.secondaryBtn} onClick={handleDownloadJson}>
            <Download size={14} /> Download JSON
          </button>
          <button
            className={styles.publishCtaBtn}
            onClick={handleStartPublish}
            title={
              validationResult.isValid
                ? "Publish Lakeview dashboard to Databricks"
                : "Fix schema errors before publishing"
            }
          >
            <Rocket size={16} /> Publish to Databricks
          </button>
        </div>
      </div>

      {/* ── Main Workspace Grid ── */}
      <div className={styles.workspaceGrid}>
        <div className={styles.mainPanel}>
          {/* VIEW MODE 1: Monaco Code Editor */}
          {viewMode === "code" && (
            <div className={styles.editorCard}>
              <div className={styles.editorHeader}>
                <div className={styles.editorTitleGroup}>
                  <Code2 size={16} style={{ color: "#3b82f6" }} />
                  <span>lakeview_dashboard.lvdash.json</span>
                  <span
                    className={`${styles.editorStatusBadge} ${
                      validationResult.isValid ? styles.statusValid : styles.statusInvalid
                    }`}
                  >
                    {validationResult.isValid ? "✓ Schema Valid" : "✗ Invalid"}
                  </span>
                </div>
              </div>

              <div className={styles.monacoContainer}>
                {fetchingJson ? (
                  <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-tertiary)" }}>
                    Fetching generated Lakeview AST JSON specification...
                  </div>
                ) : (
                  <MonacoEditor
                    height="100%"
                    defaultLanguage="json"
                    theme="vs-dark"
                    value={jsonCode}
                    onChange={(val) => setJsonCode(val || "")}
                    onMount={(editor) => {
                      editorRef.current = editor;
                    }}
                    options={{
                      minimap: { enabled: true },
                      fontSize: 13,
                      fontFamily: "var(--font-family-mono, monospace)",
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                      tabSize: 2,
                      folding: true,
                      lineNumbers: "on",
                      wordWrap: "on",
                    }}
                  />
                )}
              </div>
            </div>
          )}

          {/* VIEW MODE 2: 100% Dynamic AST Tree View */}
          {viewMode === "tree" && (
            <div className={styles.treeCard}>
              <h3 className={styles.treeTitle}>
                <FolderTree size={18} style={{ color: "#3b82f6" }} /> Dashboard AST Visual Hierarchy
              </h3>

              {parsedJsonObject ? (
                <div style={{ marginLeft: "0.5rem" }}>
                  <div className={styles.treeNodeRow}>
                    <LayoutGrid size={16} className={styles.treeNodeIcon} />
                    <span className={styles.treeNodeLabel}>Dashboard Container</span>
                    <span className={styles.treeNodeBadge}>Lakeview Spec</span>
                  </div>

                  {/* Pages Node */}
                  <div className={styles.treeNode}>
                    <div className={styles.treeNodeRow}>
                      <Layers size={16} className={styles.treeNodeIcon} />
                      <span className={styles.treeNodeLabel}>
                        Pages ({parsedJsonObject.pages?.length || 0})
                      </span>
                    </div>

                    {Array.isArray(parsedJsonObject.pages) &&
                      parsedJsonObject.pages.map((p: any, pIdx: number) => (
                        <div key={pIdx} className={styles.treeNode}>
                          <div className={styles.treeNodeRow}>
                            <FileText size={15} style={{ color: "#10b981" }} />
                            <span className={styles.treeNodeLabel}>
                              Page {pIdx + 1}: {p.displayName || p.name || "Untitled Page"}
                            </span>
                          </div>

                          {/* Widgets inside Page */}
                          <div className={styles.treeNode}>
                            {Array.isArray(p.layout) &&
                              p.layout.map((w: any, wIdx: number) => (
                                <div key={wIdx} className={styles.treeNodeRow}>
                                  <BarChart3 size={14} style={{ color: "#3b82f6" }} />
                                  <span className={styles.treeNodeLabel}>
                                    Widget: {w.widgetName || w.name || `Widget #${wIdx + 1}`}
                                  </span>
                                  <span className={styles.treeNodeValue}>
                                    Grid: {w.width || 3}x{w.height || 2}
                                  </span>
                                </div>
                              ))}
                          </div>
                        </div>
                      ))}
                  </div>

                  {/* Datasets Node */}
                  {Array.isArray(parsedJsonObject.datasets) && parsedJsonObject.datasets.length > 0 && (
                    <div className={styles.treeNode} style={{ marginTop: "0.75rem" }}>
                      <div className={styles.treeNodeRow}>
                        <Database size={16} className={styles.treeNodeIcon} />
                        <span className={styles.treeNodeLabel}>
                          Datasets ({parsedJsonObject.datasets.length})
                        </span>
                      </div>
                      <div className={styles.treeNode}>
                        {parsedJsonObject.datasets.map((ds: any, dIdx: number) => (
                          <div key={dIdx} className={styles.treeNodeRow}>
                            <Database size={14} style={{ color: "#8b5cf6" }} />
                            <span className={styles.treeNodeLabel}>{ds.name || `Dataset #${dIdx + 1}`}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ padding: "2rem", color: "var(--text-tertiary)" }}>
                  No valid JSON parsed to build tree view.
                </div>
              )}
            </div>
          )}

          {/* VIEW MODE 3: Dynamic Difference Viewer */}
          {viewMode === "diff" && (
            <div className={styles.diffCard}>
              <div className={styles.diffHeader}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <GitCompare size={16} style={{ color: "#3b82f6" }} />
                  <span>Original Generated JSON vs Modified JSON</span>
                </div>
                <div className={styles.diffLegend}>
                  <span className={styles.legendAdd}>+ Added</span>
                  <span className={styles.legendDel}>- Removed</span>
                  <span className={styles.legendMod}>~ Modified</span>
                </div>
              </div>

              <div className={styles.diffBody}>
                {diffLines.map((line, idx) => {
                  let lineClass = "";
                  if (line.type === "added") lineClass = styles.diffAddedLine;
                  if (line.type === "deleted") lineClass = styles.diffRemovedLine;
                  if (line.type === "modified") lineClass = styles.diffModifiedLine;

                  return (
                    <div key={idx} className={`${styles.diffLine} ${lineClass}`}>
                      <span className={styles.diffLineNum}>{line.lineNum}</span>
                      <span>{line.content}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Interactive Publish Modal — stays open on error/success until Cancel/Close */}
      {showPublishModal && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalContent}>
            <div className={styles.modalHeader}>
              <h3 className={styles.modalTitle}>
                <Rocket size={20} style={{ color: "#10b981" }} /> Publishing to Databricks Workspace
              </h3>
              {!isPublishing && (
                <button
                  type="button"
                  style={{ background: "none", border: "none", color: "#888", cursor: "pointer" }}
                  onClick={closePublishModal}
                  aria-label="Close publish dialog"
                >
                  <X size={18} />
                </button>
              )}
            </div>

            <div className={styles.stepList}>
              <div className={`${styles.stepItem} ${publishStep >= 1 ? styles.stepDone : styles.stepPending}`}>
                <CheckCircle2 size={16} /> 1. Uploading JSON Specification to Workspace API
              </div>
              <div
                className={`${styles.stepItem} ${
                  publishStep >= 2 ? styles.stepDone : publishStep === 1 ? styles.stepActive : styles.stepPending
                }`}
              >
                <CheckCircle2 size={16} /> 2. Creating Lakeview Dashboard Object Container
              </div>
              <div
                className={`${styles.stepItem} ${
                  publishStep >= 3 ? styles.stepDone : publishStep === 2 ? styles.stepActive : styles.stepPending
                }`}
              >
                <CheckCircle2 size={16} /> 3. Generating {objectCounts.widgets || 13} Visual Widgets & Grid Layout
              </div>
              <div
                className={`${styles.stepItem} ${
                  publishStep >= 4 ? styles.stepDone : publishStep === 3 ? styles.stepActive : styles.stepPending
                }`}
              >
                <CheckCircle2 size={16} /> 4. Binding SQL Queries to Unity Catalog Tables
              </div>
              <div
                className={`${styles.stepItem} ${
                  publishStep >= 5 ? styles.stepDone : publishStep === 4 ? styles.stepActive : styles.stepPending
                }`}
              >
                <CheckCircle2 size={16} /> 5. Setting Access Permissions & Finalizing
              </div>
            </div>

            {publishError && (
              <div style={{ background: "rgba(231, 76, 60, 0.1)", border: "1px solid rgba(231, 76, 60, 0.3)", borderRadius: "8px", padding: "1rem", marginTop: "1rem" }}>
                <div style={{ color: "var(--accent-red)", fontWeight: 700, fontSize: "0.85rem", marginBottom: "0.4rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <AlertTriangle size={16} /> Databricks Deployment Failed
                </div>
                <div style={{ fontSize: "0.785rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
                  {publishError}
                </div>
                {hasSavedToken && !needsCredentials && (
                  <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", marginBottom: "0.5rem" }}>
                    Using your saved default Databricks connection / server .env credentials.
                  </div>
                )}
                {needsCredentials && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <div style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
                      Server could not resolve host / warehouse / PAT from Connections or .env. Enter overrides below, or mark a connection as default under Connections.
                    </div>
                    <label style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", fontWeight: 600 }}>
                      Databricks Host
                    </label>
                    <input
                      type="text"
                      placeholder={connectionInfo.host || "https://xxx.cloud.databricks.com"}
                      value={hostOverrideInput}
                      onChange={(e) => setHostOverrideInput(e.target.value)}
                      style={{
                        background: "#0d1117",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "4px",
                        padding: "0.4rem 0.6rem",
                        color: "#fff",
                        fontSize: "0.8rem",
                      }}
                    />
                    <label style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", fontWeight: 600 }}>
                      SQL Warehouse ID
                    </label>
                    <input
                      type="text"
                      placeholder={connectionInfo.warehouse_id || "abc123def456..."}
                      value={warehouseOverrideInput}
                      onChange={(e) => setWarehouseOverrideInput(e.target.value)}
                      style={{
                        background: "#0d1117",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "4px",
                        padding: "0.4rem 0.6rem",
                        color: "#fff",
                        fontSize: "0.8rem",
                      }}
                    />
                    <label style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", fontWeight: 600 }}>
                      {hasSavedToken ? "Override PAT (optional)" : "Databricks Personal Access Token (PAT)"}
                    </label>
                    <input
                      type="password"
                      placeholder={hasSavedToken ? "leave blank to use saved token" : "dapi..."}
                      value={patTokenInput}
                      onChange={(e) => setPatTokenInput(e.target.value)}
                      style={{
                        background: "#0d1117",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "4px",
                        padding: "0.4rem 0.6rem",
                        color: "#fff",
                        fontSize: "0.8rem",
                      }}
                    />
                  </div>
                )}
                <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
                  <button
                    type="button"
                    className={styles.secondaryBtn}
                    onClick={handleStartPublish}
                    disabled={isPublishing}
                    style={{ background: "var(--accent-cyan)", color: "#000", border: "none", fontWeight: 700 }}
                  >
                    Retry Publish
                  </button>
                  <button
                    type="button"
                    className={styles.secondaryBtn}
                    onClick={closePublishModal}
                    disabled={isPublishing}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {publishComplete && (
              <div className={styles.completedBox}>
                <div className={styles.completedTitle}>Dashboard Published Successfully!</div>
                <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0 }}>
                  Your Lakeview dashboard is now live in Databricks.
                </p>
                {publishWarning && (
                  <div style={{ fontSize: "0.75rem", color: "#f59e0b", marginTop: "0.5rem" }}>
                    {publishWarning}
                  </div>
                )}
                {publishedDashboardUrl ? (
                  <a
                    href={publishedDashboardUrl}
                    target="_blank"
                    rel="noreferrer"
                    className={styles.databricksLinkBtn}
                  >
                    <ExternalLink size={16} /> Open Published Dashboard in Databricks
                  </a>
                ) : (
                  <a
                    href={connectionInfo.host.startsWith("http") ? connectionInfo.host : `https://${connectionInfo.host}`}
                    target="_blank"
                    rel="noreferrer"
                    className={styles.databricksLinkBtn}
                  >
                    <ExternalLink size={16} /> Open Databricks Workspace
                  </a>
                )}
                <button
                  type="button"
                  className={styles.secondaryBtn}
                  style={{ marginTop: "0.5rem" }}
                  onClick={closePublishModal}
                >
                  Close Review Panel
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
