"use client";

import { useState, useEffect } from "react";
import { Sparkles, Database, ArrowRight, CheckCircle2, RefreshCw, FileSpreadsheet } from "lucide-react";
import CatalogBrowser from "@/components/mapping/CatalogBrowser";
import { useToast } from "@/components/ui/ToastProvider";
import {
  getJobDatasources,
  discoverMappings,
  saveMappings,
  autoUploadEmbedded,
  executePipeline,
  listConnections,
} from "@/lib/api";
import type { TableauDatasourceInfo, EmbeddedFileInfo, DatasourceMappingItem } from "@/lib/types";
import styles from "./InlineMappingPanel.module.css";

interface InlineMappingPanelProps {
  jobUuid: string;
  onExecute?: () => void;
}

export default function InlineMappingPanel({ jobUuid, onExecute }: InlineMappingPanelProps) {
  const { success, info, error: toastError } = useToast();
  const [loading, setLoading] = useState(true);
  const [datasources, setDatasources] = useState<TableauDatasourceInfo[]>([]);
  const [embeddedFiles, setEmbeddedFiles] = useState<EmbeddedFileInfo[]>([]);
  const [mappings, setMappings] = useState<Record<string, DatasourceMappingItem>>({});
  const [suggestions, setSuggestions] = useState<Record<string, any>>({});
  const [activeMappingTable, setActiveMappingTable] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [saving, setSaving] = useState(false);

  // Databricks Connection Settings
  const [host, setHost] = useState("");
  const [token, setToken] = useState("");
  const [warehouseId, setWarehouseId] = useState("a1b2c3d4e5f67890");

  useEffect(() => {
    async function initConnection() {
      try {
        const conns = await listConnections();
        if (conns && conns.length > 0) {
          const def = conns.find((c) => c.is_default) || conns[0];
          setHost(def.host);
          setToken(def.token_full || def.token);
          if (def.warehouse_id) setWarehouseId(def.warehouse_id);
          return;
        }
      } catch {}

      const saved = localStorage.getItem("lakeview_connections");
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          if (parsed.length > 0) {
            setHost(parsed[0].host);
            setToken(parsed[0].token_full || parsed[0].token);
            setWarehouseId(parsed[0].warehouseId || warehouseId);
          }
        } catch {}
      }
    }
    initConnection();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await getJobDatasources(jobUuid);
      setDatasources(res.datasources || []);
      setEmbeddedFiles(res.embedded_files || []);

      const initial: Record<string, DatasourceMappingItem> = {};
      for (const ds of res.datasources || []) {
        for (const t of ds.tables) {
          const ex =
            res.existing_mappings?.[t.name] ||
            res.existing_mappings?.[t.clean_name] ||
            res.existing_mappings?.[t.raw_name] ||
            (t.uc_fqn ? res.existing_mappings?.[t.uc_fqn.split(".").pop() || ""] : undefined) ||
            // legacy key when "*.csv" was wrongly normalized to "Csv"
            (/\.csv$/i.test(t.raw_name || "") ? res.existing_mappings?.["Csv"] : undefined);
          // Prefer embedded UC FQN from live Databricks relation, then connection catalog.
          // Compute autoTarget even when a saved target exists — only CONFIRMED
          // mappings are sacred.  This ensures stale PENDING mappings on deployed
          // systems still get promoted to AUTO_DETECTED.
          let autoTarget = "";
          let autoStatus: any = "PENDING";
          const savedIsConfirmed = (ex?.status || "").toUpperCase() === "CONFIRMED";
          if (!savedIsConfirmed && t.uc_fqn) {
            autoTarget = t.uc_fqn;
            autoStatus = "AUTO_DETECTED";
          } else if (!savedIsConfirmed && ds.is_databricks && ds.databricks_connection?.catalog) {
            const cat = ds.databricks_connection.catalog;
            const sch = ds.databricks_connection.schema || "default";
            const cleanName = t.clean_name || t.name;
            autoTarget = `${cat}.${sch}.${cleanName}`;
            autoStatus = "AUTO_DETECTED";
          }
          // Determine effective target: saved target wins, then autoTarget, then fallback
          const effectiveTarget = ex?.target_full_name || autoTarget || (t.is_unresolved ? "" : t.name);

          // Determine effective status:
          // - CONFIRMED is authoritative — never demote
          // - PENDING with an autoTarget → promote to AUTO_DETECTED
          // - Otherwise use saved status or derive from context
          let effectiveStatus: string = ex?.status || "PENDING";
          if (effectiveStatus === "CONFIRMED") {
            // keep CONFIRMED
          } else if (autoTarget) {
            effectiveStatus = "AUTO_DETECTED";
          } else if (effectiveTarget && effectiveStatus === "PENDING") {
            effectiveStatus = "PENDING";
          }

          initial[t.name] = {
            tableau_datasource_name: ds.name,
            tableau_table_name: t.name,
            tableau_connection_type: ds.connection_type,
            target_full_name: effectiveTarget,
            status: effectiveStatus as any,
            confidence_score: ex?.confidence_score,
          };
        }
      }
      setMappings(initial);
    } catch (err: any) {
      toastError(err.message || "Failed to load datasources.", "Error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [jobUuid]);

  const handleDiscover = async () => {
    if (!host || !token) {
      toastError("Configure a Databricks Connection in the Connections page first.", "Connection Required");
      return;
    }
    setDiscovering(true);
    try {
      const res = await discoverMappings(jobUuid, host, token, warehouseId);
      setSuggestions(res.suggestions || {});

      const updated = { ...mappings };
      let applied = 0;
      for (const [tblName, sug] of Object.entries(res.suggestions || {})) {
        if (sug.matches && sug.matches.length > 0) {
          const top = sug.matches[0];
          if (top.confidence_score >= 0.7 && !updated[tblName]?.target_full_name) {
            updated[tblName] = { ...updated[tblName], target_full_name: top.target_full_name, confidence_score: top.confidence_score, status: "MATCHED" };
            applied++;
          }
        }
      }
      setMappings(updated);
      success(`Discovered ${res.uc_table_count} UC tables. Auto-matched ${applied} sources.`, "Discovery Complete");
    } catch (err: any) {
      toastError(err.message || "Discovery failed.", "Error");
    } finally {
      setDiscovering(false);
    }
  };

  const handleAutoUpload = async () => {
    if (!host || !token) { toastError("Configure a Databricks Connection first.", "Connection Required"); return; }
    try {
      const res = await autoUploadEmbedded(jobUuid, host, token, warehouseId, "main", "default");
      const updated = { ...mappings };
      for (const r of res.results || []) {
        if (r.status === "SUCCESS") {
          for (const k of Object.keys(updated)) {
            if (k.toLowerCase().includes(r.table_name.toLowerCase())) {
              updated[k] = { ...updated[k], target_full_name: r.full_name, status: "CONFIRMED" };
            }
          }
        }
      }
      setMappings(updated);
      success(`Created ${res.uploaded_count} Delta tables.`, "Upload Complete");
    } catch (err: any) {
      toastError(err.message || "Upload failed.", "Error");
    }
  };

  const handleSelectTarget = (tblName: string, fullName: string) => {
    setMappings((prev) => ({ ...prev, [tblName]: { ...prev[tblName], target_full_name: fullName, status: "CONFIRMED" } }));
    setActiveMappingTable(null);
    success(`Mapped '${tblName}' → '${fullName}'`, "Mapping Confirmed");
  };

  const handleDirectExecute = async () => {
    setSaving(true);
    try {
      if (totalCount > 0) {
        const list = Object.values(mappings).map((m) =>
          m.target_full_name ? { ...m, status: "CONFIRMED" as const } : m
        );
        await saveMappings(jobUuid, list);
      }
      if (onExecute) {
        onExecute();
      } else {
        await executePipeline(jobUuid);
      }
      success("Pipeline execution started.", "Executing");
    } catch (err: any) {
      toastError(err.message || "Failed to execute pipeline.", "Error");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAndExecute = async () => {
    // Promote Auto-Detected / Matched rows to CONFIRMED so /execute loads them.
    const list = Object.values(mappings).map((m) =>
      m.target_full_name ? { ...m, status: "CONFIRMED" as const } : m
    );
    const unmapped = list.filter((m) => !m.target_full_name);
    if (unmapped.length > 0) {
      toastError(`${unmapped.length} datasource(s) still unmapped.`, "Incomplete");
      return;
    }
    setSaving(true);
    try {
      await saveMappings(jobUuid, list);
      setMappings((prev) => {
        const next = { ...prev };
        for (const m of list) {
          next[m.tableau_table_name] = m;
        }
        return next;
      });
      if (onExecute) {
        onExecute();
      } else {
        await executePipeline(jobUuid);
      }
      success("Mappings saved. Pipeline started.", "Executing");
    } catch (err: any) {
      toastError(err.message || "Failed to save/execute.", "Error");
    } finally {
      setSaving(false);
    }
  };

  const totalCount = Object.keys(mappings).length;
  const mappedCount = Object.values(mappings).filter((m) => m.target_full_name).length;
  const progressPct = totalCount > 0 ? (mappedCount / totalCount) * 100 : 100;
  const isComplete = totalCount === 0 || (totalCount > 0 && mappedCount === totalCount);

  if (loading) {
    return <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.875rem" }}>Loading datasources...</div>;
  }

  if (datasources.length === 0) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <span className={styles.headerTitle}>Datasource → Unity Catalog Mapping</span>
          <button className={styles.actionBtnPrimary} onClick={handleDirectExecute} disabled={saving}>
            {saving ? <RefreshCw size={13} className="spin" /> : <ArrowRight size={13} />}
            {saving ? "Starting..." : "Run Pipeline →"}
          </button>
        </div>
        <div style={{ padding: "2rem", textAlign: "center", background: "var(--bg-surface)", borderRadius: "var(--radius-lg)", border: "1px solid var(--border-subtle)", marginTop: "1rem" }}>
          <CheckCircle2 size={32} color="var(--accent-green)" style={{ margin: "0 auto 0.75rem", display: "block" }} />
          <h4 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
            No Table Mappings Required
          </h4>
          <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", maxWidth: "480px", margin: "0 auto 1.25rem" }}>
            All datasources in this workbook connect directly to Databricks Unity Catalog or do not require manual table mapping. You can proceed directly to pipeline execution.
          </p>
          <button className={styles.actionBtnPrimary} onClick={handleDirectExecute} disabled={saving}>
            {saving ? <RefreshCw size={13} className="spin" /> : <ArrowRight size={13} />}
            {saving ? "Starting..." : "Run Pipeline →"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.headerTitle}>Datasource → Unity Catalog Mapping</span>
        <div className={styles.headerActions}>
          {embeddedFiles.length > 0 && (
            <button className={styles.actionBtn} onClick={handleAutoUpload}>
              <FileSpreadsheet size={13} /> Auto-Upload ({embeddedFiles.length})
            </button>
          )}
          <button className={styles.actionBtn} onClick={handleDiscover} disabled={discovering}>
            {discovering ? <RefreshCw size={13} className="spin" /> : <Sparkles size={13} />}
            {discovering ? "Discovering..." : "Auto-Discover"}
          </button>
          <button className={styles.actionBtnPrimary} onClick={handleSaveAndExecute} disabled={!isComplete || saving}>
            {saving ? <RefreshCw size={13} className="spin" /> : <ArrowRight size={13} />}
            {saving ? "Saving..." : "Save & Execute"}
          </button>
        </div>
      </div>

      <div className={styles.mainGrid}>
        {/* Left: mapping list */}
        <div className={styles.mappingList}>
          {datasources.map((ds) =>
            ds.tables.map((t) => {
              const mapItem = mappings[t.name];
              const target = mapItem?.target_full_name;
              const isSelected = activeMappingTable === t.name;
              const sug = suggestions[t.name];

              return (
                <div key={t.name} className={isSelected ? styles.mappingCardSelected : styles.mappingCard}>
                  <div className={styles.sourceRow}>
                    <span className={styles.sourceName}>{t.name}</span>
                    {target ? (
                      mapItem?.status === "AUTO_DETECTED" ? (
                        <span className={styles.mappedBadge} style={{ background: "rgba(16, 185, 129, 0.15)", color: "#10b981" }}>✓ Auto-Detected</span>
                      ) : (
                        <span className={styles.mappedBadge}>Mapped</span>
                      )
                    ) : (
                      <span className={styles.unmappedBadge}>Unmapped</span>
                    )}
                    </div>
                    <div className={styles.sourceType}>
                      {ds.is_databricks
                        ? `Databricks • ${ds.databricks_connection?.catalog || "UC"}.${ds.databricks_connection?.schema || "default"} • ${ds.column_count} cols`
                        : `${ds.caption || ds.name} • ${ds.connection_type} • ${ds.column_count} cols`}
                    </div>
                    {ds.is_databricks && ds.databricks_connection?.host && (
                      <div className={styles.sourceType} style={{ fontSize: "0.7rem", opacity: 0.85 }}>
                        {ds.databricks_connection.host.replace(/^https?:\/\//, "")}
                        {ds.databricks_connection.warehouse_id
                          ? ` • warehouse ${ds.databricks_connection.warehouse_id}`
                          : ""}
                      </div>
                    )}
                  <div className={styles.targetRow}>
                    <Database size={13} color={target ? "var(--accent-cyan)" : "var(--text-disabled)"} />
                    {target ? (
                      <span className={styles.targetName}>{target}</span>
                    ) : (
                      <span className={styles.unmapped}>No target selected</span>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: "0.25rem", marginTop: "0.25rem" }}>
                    {sug?.matches?.[0] && !target && (
                      <button className={styles.selectBtn} onClick={() => handleSelectTarget(t.name, sug.matches[0].target_full_name)}>
                        <CheckCircle2 size={11} /> Accept ({Math.round(sug.matches[0].confidence_score * 100)}%)
                      </button>
                    )}
                    <button className={styles.selectBtn} onClick={() => setActiveMappingTable(isSelected ? null : t.name)}>
                      {isSelected ? "Cancel" : target ? "Change" : "Select →"}
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Right: catalog browser */}
        <div className={styles.browserColumn}>
          <CatalogBrowser
            host={host}
            token={token}
            warehouseId={warehouseId}
            selectedTable={activeMappingTable ? mappings[activeMappingTable]?.target_full_name : undefined}
            onSelectTable={(fullName) => {
              if (activeMappingTable) {
                handleSelectTarget(activeMappingTable, fullName);
              } else {
                info("Select a datasource on the left first.", "No Source Selected");
              }
            }}
          />
        </div>
      </div>

      {/* Progress */}
      <div className={styles.progressRow}>
        <span className={styles.progressText}>
          {mappedCount}/{totalCount} mapped
        </span>
        <div className={styles.progressBar}>
          <div className={styles.progressFill} style={{ width: `${progressPct}%` }} />
        </div>
      </div>

      {/* Auto Databricks Detection Summary */}
      {host && (
        <div className={styles.autoDetectBanner}>
          <div>
            <div className={styles.autoDetectTitle}>
              <Sparkles size={16} /> Auto-Detected Databricks Workspace Connection
            </div>
            <div className={styles.autoDetectDesc}>
              Target: <strong style={{ color: "var(--text-primary)" }}>{host}</strong> • Catalog: <strong style={{ color: "var(--text-primary)" }}>main</strong> • Warehouse: <strong style={{ color: "var(--text-primary)" }}>{warehouseId}</strong>
            </div>
          </div>
          <span className={styles.mappedBadge}>Active Connection</span>
        </div>
      )}

      {/* Target Databricks Table Mapping Lineage */}
      <div style={{ marginTop: "1.5rem" }}>
        <h4 style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
          Target Databricks Table Mapping Lineage
        </h4>
        {Object.keys(mappings).length > 0 ? (
          <table className={styles.columnTable}>
            <thead>
              <tr>
                <th>Source Table</th>
                <th>Connection Type</th>
                <th>Target Databricks Table (Unity Catalog)</th>
                <th>Mapping Status</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {Object.values(mappings).map((item, idx) => {
                const target = item.target_full_name || "Unmapped";
                const isMapped = Boolean(item.target_full_name);
                const confPct = item.confidence_score ? Math.round(item.confidence_score * 100) : isMapped ? 100 : 0;

                return (
                  <tr key={idx}>
                    <td style={{ fontWeight: 600 }}>{item.tableau_table_name}</td>
                    <td>
                      <span style={{ color: "var(--text-secondary)", fontWeight: 500, fontSize: "0.75rem" }}>
                        {item.tableau_connection_type || "Relational"}
                      </span>
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", color: isMapped ? "var(--accent-cyan)" : "var(--text-tertiary)" }}>
                      {target}
                    </td>
                    <td>
                      <span className={isMapped ? styles.transformBadge : styles.unmappedBadge}>
                        {item.status === "AUTO_DETECTED"
                          ? "Auto-Detected"
                          : item.status === "MATCHED"
                          ? "Catalog Matched"
                          : isMapped
                          ? "Confirmed"
                          : "Pending"}
                      </span>
                    </td>
                    <td>
                      <span className={confPct >= 80 ? styles.confidenceBadgeHigh : styles.unmappedBadge}>
                        {confPct}%
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div style={{ fontSize: "0.8rem", color: "var(--text-tertiary)", fontStyle: "italic" }}>
            No table mappings found for this migration job.
          </div>
        )}
      </div>
    </div>
  );
}
