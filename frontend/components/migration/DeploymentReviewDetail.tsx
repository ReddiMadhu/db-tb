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
}

export default function DeploymentReviewDetail({
  jobUuid,
  stage,
  onSelectNextStage,
}: DeploymentReviewDetailProps) {
  const artifacts = (stage?.artifacts || {}) as Record<string, any>;
  const metrics = (stage?.metrics || {}) as Record<string, any>;

  // Dynamic initial JSON string from stage code/artifacts
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
  const [fetchingJson, setFetchingJson] = useState<boolean>(!rawJsonFromStage);

  // Active Connection Info
  const [connectionInfo, setConnectionInfo] = useState<{
    host: string;
    warehouse_id: string;
    catalog: string;
    schema_name: string;
  }>({
    host: artifacts.workspace || "Databricks Workspace",
    warehouse_id: artifacts.warehouse_id || "Serverless Warehouse",
    catalog: artifacts.catalog || "main",
    schema_name: artifacts.schema_name || "default",
  });

  // Fetch real JSON if missing in props
  useEffect(() => {
    if (!jsonCode && jobUuid) {
      setFetchingJson(true);
      getLakeviewJson(jobUuid)
        .then((data) => {
          const str = JSON.stringify(data, null, 2);
          setJsonCode(str);
          setOriginalJsonStr(str);
        })
        .catch(() => {
          // If endpoint fails, construct dynamic fallback from stage artifacts
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
    }
  }, [jobUuid, jsonCode, artifacts]);

  // Fetch active Databricks connection details dynamically
  useEffect(() => {
    getDefaultConnection()
      .then((res) => {
        if (res.has_default && res.connection) {
          setConnectionInfo({
            host: res.connection.host || "dbc-prod.cloud.databricks.com",
            warehouse_id: res.connection.warehouse_id || "Serverless SQL",
            catalog: res.connection.catalog || "main",
            schema_name: res.connection.schema_name || "analytics",
          });
        }
      })
      .catch(() => {});
  }, []);

  const [viewMode, setViewMode] = useState<"code" | "tree" | "diff">("code");
  const editorRef = useRef<any>(null);

  // Publish Modal state
  const [isPublishing, setIsPublishing] = useState<boolean>(false);
  const [publishStep, setPublishStep] = useState<number>(0);
  const [publishComplete, setPublishComplete] = useState<boolean>(false);

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

  const [publishError, setPublishError] = useState<string | null>(null);
  const [patTokenInput, setPatTokenInput] = useState<string>("");
  const [publishedDashboardUrl, setPublishedDashboardUrl] = useState<string | null>(artifacts.published_url || null);

  // Handle Publish flow to Databricks API
  const handleStartPublish = async () => {
    if (!validationResult.isValid) {
      alert("Please fix schema errors before publishing to Databricks.");
      return;
    }
    setIsPublishing(true);
    setPublishStep(1);
    setPublishError(null);
    setPublishComplete(false);

    try {
      setPublishStep(2);
      const whId = connectionInfo.warehouse_id && !connectionInfo.warehouse_id.includes("Serverless")
        ? connectionInfo.warehouse_id
        : "6ad2e493737245a5";
      
      const hostUrl = connectionInfo.host && !connectionInfo.host.includes("Workspace")
        ? connectionInfo.host
        : undefined;

      setPublishStep(3);
      const res = await deployToDatabricks(jobUuid, {
        warehouse_id: whId,
        host: hostUrl,
        token: patTokenInput || undefined,
        catalog: connectionInfo.catalog || undefined,
        schema_name: connectionInfo.schema_name || undefined,
      });

      setPublishStep(4);
      setTimeout(() => {
        setPublishStep(5);
        setPublishComplete(true);
        if (res.published_url) {
          setPublishedDashboardUrl(res.published_url);
        }
      }, 500);
    } catch (err: any) {
      setPublishError(err.message || "Databricks deployment failed. Please verify your host URL and PAT token.");
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
          <button className={styles.secondaryBtn} onClick={handleFormatJson} title="Format JSON Code">
            <Sparkles size={14} /> Format
          </button>
          <button className={styles.secondaryBtn} onClick={handleReset} title="Reset to original JSON">
            <RotateCcw size={14} /> Reset
          </button>
          <button className={styles.secondaryBtn} onClick={handleCopy}>
            <Copy size={14} /> Copy
          </button>
          <button className={styles.secondaryBtn} onClick={handleDownloadJson}>
            <Download size={14} /> Download JSON
          </button>
          <button className={styles.publishCtaBtn} onClick={handleStartPublish}>
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
                <div className={styles.editorTools}>
                  <button className={styles.editorToolBtn} onClick={handleFormatJson}>
                    Auto-Format
                  </button>
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

      {/* Interactive Publish Modal */}
      {isPublishing && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalContent}>
            <div className={styles.modalHeader}>
              <h3 className={styles.modalTitle}>
                <Rocket size={20} style={{ color: "#10b981" }} /> Publishing to Databricks Workspace
              </h3>
              {!publishComplete && (
                <button
                  style={{ background: "none", border: "none", color: "#888", cursor: "pointer" }}
                  onClick={() => setIsPublishing(false)}
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
                <CheckCircle2 size={16} /> 3. Generating {objectCounts.widgets} Visual Widgets & Grid Layout
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
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                  <label style={{ fontSize: "0.72rem", color: "var(--text-tertiary)", fontWeight: 600 }}>
                    Enter Databricks Personal Access Token (PAT):
                  </label>
                  <input
                    type="password"
                    placeholder="dapi..."
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
                  <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.4rem" }}>
                    <button
                      className={styles.secondaryBtn}
                      onClick={handleStartPublish}
                      style={{ background: "var(--accent-cyan)", color: "#000", border: "none", fontWeight: 700 }}
                    >
                      Retry Publish
                    </button>
                    <button
                      className={styles.secondaryBtn}
                      onClick={() => setIsPublishing(false)}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}

            {publishComplete && (
              <div className={styles.completedBox}>
                <div className={styles.completedTitle}>🎉 Dashboard Published Successfully!</div>
                <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0 }}>
                  Your Lakeview dashboard is now live in Databricks.
                </p>
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
                  className={styles.secondaryBtn}
                  style={{ marginTop: "0.5rem" }}
                  onClick={() => setIsPublishing(false)}
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
