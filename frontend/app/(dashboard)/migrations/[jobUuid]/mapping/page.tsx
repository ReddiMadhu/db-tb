"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Upload,
  Database,
  RefreshCw,
  Loader2,
  FileSpreadsheet,
  ArrowRightLeft,
} from "lucide-react";
import Button from "@/components/ui/Button";
import Badge from "@/components/ui/Badge";
import CatalogBrowser from "@/components/mapping/CatalogBrowser";
import UploadTableModal from "@/components/mapping/UploadTableModal";
import { useToast } from "@/components/ui/ToastProvider";
import { useAsyncOperation } from "@/components/providers/AsyncOperationProvider";
import {
  getJobDatasources,
  discoverMappings,
  saveMappings,
  validateMappings,
  autoUploadEmbedded,
  executePipeline,
} from "@/lib/api";
import type {
  TableauDatasourceInfo,
  EmbeddedFileInfo,
  DatasourceMappingItem,
} from "@/lib/types";
import styles from "./Mapping.module.css";

export default function DatasourceMappingPage({
  params,
}: {
  params: Promise<{ jobUuid: string }>;
}) {
  const { jobUuid } = use(params);
  const router = useRouter();
  const { toast, success, info, error: toastError } = useToast();
  const { startOperation, updateProgress, finishSuccess, finishError } = useAsyncOperation();

  const [loading, setLoading] = useState(true);
  const [datasources, setDatasources] = useState<TableauDatasourceInfo[]>([]);
  const [embeddedFiles, setEmbeddedFiles] = useState<EmbeddedFileInfo[]>([]);
  const [mappings, setMappings] = useState<Record<string, DatasourceMappingItem>>({});
  const [suggestions, setSuggestions] = useState<Record<string, any>>({});
  const [activeMappingTable, setActiveMappingTable] = useState<string | null>(null);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadTargetTable, setUploadTargetTable] = useState<string>("");

  // Databricks Connection Settings (read from localStorage)
  const [host, setHost] = useState("");
  const [token, setToken] = useState("");
  const [warehouseId, setWarehouseId] = useState("a1b2c3d4e5f67890");

  useEffect(() => {
    const saved = localStorage.getItem("lakeview_connections");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.length > 0) {
          setHost(parsed[0].host);
          setToken(parsed[0].token);
          setWarehouseId(parsed[0].warehouseId || warehouseId);
        }
      } catch {}
    }
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await getJobDatasources(jobUuid);
      setDatasources(res.datasources || []);
      setEmbeddedFiles(res.embedded_files || []);

      // Pre-fill existing mappings
      const initial: Record<string, DatasourceMappingItem> = {};
      for (const ds of res.datasources || []) {
        for (const t of ds.tables) {
          const ex = res.existing_mappings?.[t.name];
          initial[t.name] = {
            tableau_datasource_name: ds.name,
            tableau_table_name: t.name,
            tableau_connection_type: ds.connection_type,
            target_full_name: ex?.target_full_name || (t.is_unresolved ? "" : t.name),
            status: (ex?.status as any) || (ex?.target_full_name ? "CONFIRMED" : "PENDING"),
          };
        }
      }
      setMappings(initial);
    } catch (err: any) {
      toastError(err.message || "Failed to load job datasources.", "Error Loading");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [jobUuid]);

  const handleDiscover = async () => {
    if (!host || !token) {
      toastError("Please configure a Databricks Connection in the Connections page first.", "Connection Required");
      return;
    }

    const opId = startOperation({
      title: "Discovering Databricks Metadata",
      stageText: "Querying Unity Catalog API",
      taskDescription: "Scanning workspace tables and auto-matching Tableau data sources...",
    });

    try {
      updateProgress(opId, 50, "Auto-Matching", "Comparing table name similarity...");
      const res = await discoverMappings(jobUuid, host, token, warehouseId);
      setSuggestions(res.suggestions || {});

      // Auto-apply high confidence matches
      const updated = { ...mappings };
      let applied = 0;

      for (const [tblName, sug] of Object.entries(res.suggestions || {})) {
        if (sug.matches && sug.matches.length > 0) {
          const top = sug.matches[0];
          if (top.confidence_score >= 0.7 && !updated[tblName]?.target_full_name) {
            updated[tblName] = {
              ...updated[tblName],
              target_full_name: top.target_full_name,
              confidence_score: top.confidence_score,
              status: "MATCHED",
            };
            applied++;
          }
        }
      }
      setMappings(updated);

      finishSuccess(opId, {
        title: "Metadata Discovery Complete",
        description: `Discovered ${res.uc_table_count} Unity Catalog tables. Auto-matched ${applied} data sources.`,
      });
    } catch (err: any) {
      finishError(opId, {
        title: "Discovery Failed",
        message: err.message || "Failed to connect to Unity Catalog.",
      });
    }
  };

  const handleAutoUpload = async () => {
    if (!host || !token) {
      toastError("Please configure a Databricks Connection first.", "Connection Required");
      return;
    }

    const opId = startOperation({
      title: "Auto-Extracting & Uploading Embedded Data",
      stageText: "Extracting from .twbx Archive",
      taskDescription: "Converting embedded Excel/CSV files and creating Delta tables in Unity Catalog...",
    });

    try {
      updateProgress(opId, 40, "Uploading to UC Volume", "Transferring data files to /Volumes/main/default/lakeshift_staging...");
      const res = await autoUploadEmbedded(jobUuid, host, token, warehouseId, "main", "default");

      const updated = { ...mappings };
      for (const r of res.results || []) {
        if (r.status === "SUCCESS") {
          // Find matching mapping item
          for (const k of Object.keys(updated)) {
            if (k.toLowerCase().includes(r.table_name.toLowerCase()) || r.table_name.includes(k.toLowerCase().replace(/[^a-z0-9]/g, ""))) {
              updated[k] = {
                ...updated[k],
                target_full_name: r.full_name,
                status: "CONFIRMED",
              };
            }
          }
        }
      }
      setMappings(updated);

      finishSuccess(opId, {
        title: "Auto-Upload Completed",
        description: `Successfully created ${res.uploaded_count} Delta tables in Unity Catalog.`,
      });
    } catch (err: any) {
      finishError(opId, {
        title: "Auto-Upload Failed",
        message: err.message || "Failed to extract and upload embedded files.",
      });
    }
  };

  const handleSelectTarget = (tblName: string, fullName: string) => {
    setMappings((prev) => ({
      ...prev,
      [tblName]: {
        ...prev[tblName],
        target_full_name: fullName,
        status: "CONFIRMED",
      },
    }));
    setActiveMappingTable(null);
    success(`Mapped '${tblName}' → '${fullName}'`, "Mapping Confirmed");
  };

  const handleSaveAndExecute = async () => {
    const list = Object.values(mappings);
    const unmapped = list.filter((m) => !m.target_full_name);

    if (unmapped.length > 0) {
      toastError(`Please map all ${list.length} datasources before executing. (${unmapped.length} unmapped remaining)`, "Mapping Incomplete");
      return;
    }

    const opId = startOperation({
      title: "Saving Mappings & Executing Migration Pipeline",
      stageText: "Saving Table Mappings",
      taskDescription: "Persisting confirmed catalog.schema.table references and starting 10-stage pipeline...",
    });

    try {
      // 1. Save mappings
      await saveMappings(jobUuid, list);

      // 2. Validate mappings live against UC if credentials provided
      if (host && token) {
        updateProgress(opId, 30, "Validating Tables", "Verifying mapped tables exist in Unity Catalog...");
        const valRes = await validateMappings(jobUuid, host, token);
        if (!valRes.valid) {
          finishError(opId, {
            title: "Validation Failed",
            message: `Mapped table validation failed: ${valRes.errors.join(", ")}`,
          });
          return;
        }
      }

      // 3. Execute 10-Stage Pipeline
      updateProgress(opId, 60, "Transpiling Spark SQL", "Compiling formulas with resolved Unity Catalog tables...");
      await executePipeline(jobUuid);

      finishSuccess(opId, {
        title: "Pipeline Execution Completed!",
        description: "Dashboard layout and executable Spark SQL generated with 100% table resolution.",
        primaryActionLabel: "View Migration Workspace",
        onPrimaryAction: () => router.push(`/migrations/${jobUuid}`),
      });

      router.push(`/migrations/${jobUuid}`);
    } catch (err: any) {
      finishError(opId, {
        title: "Execution Failed",
        message: err.message || "Failed to execute migration pipeline.",
      });
    }
  };

  const totalCount = Object.keys(mappings).length;
  const mappedCount = Object.values(mappings).filter((m) => m.target_full_name).length;
  const isComplete = totalCount > 0 && mappedCount === totalCount;
  const progressPct = totalCount > 0 ? (mappedCount / totalCount) * 100 : 0;

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Datasource Discovery & Mapping</h1>
          <p className={styles.subtitle}>
            Map every Tableau data source to a verified Unity Catalog table before SQL generation.
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem" }}>
          {embeddedFiles.length > 0 && (
            <Button
              variant="secondary"
              icon={<FileSpreadsheet size={16} color="var(--accent-green)" />}
              onClick={handleAutoUpload}
            >
              Auto-Upload ({embeddedFiles.length} embedded)
            </Button>
          )}

          <Button
            variant="secondary"
            icon={<Sparkles size={16} color="var(--accent-orange)" />}
            onClick={handleDiscover}
          >
            Auto-Discover Matches
          </Button>
        </div>
      </div>

      {/* Main 2-Column Layout */}
      <div className={styles.mainGrid}>
        {/* Left Column: Tableau Datasources List */}
        <div className={styles.panel}>
          {loading ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-tertiary)" }}>
              <Loader2 size={24} className="spin" />
              <p style={{ marginTop: "0.5rem" }}>Extracting datasources from workbook...</p>
            </div>
          ) : datasources.length === 0 ? (
            <div className={styles.card}>
              <p style={{ color: "var(--text-tertiary)", margin: 0 }}>No datasources found in workbook.</p>
            </div>
          ) : (
            datasources.map((ds) =>
              ds.tables.map((t) => {
                const mapItem = mappings[t.name];
                const target = mapItem?.target_full_name;
                const sug = suggestions[t.name];
                const isSelectedForMapping = activeMappingTable === t.name;

                return (
                  <div
                    key={t.name}
                    className={styles.card}
                    style={{
                      borderColor: isSelectedForMapping
                        ? "var(--accent-orange)"
                        : target
                        ? "var(--border-default)"
                        : "var(--accent-amber)",
                    }}
                  >
                    <div className={styles.cardHeader}>
                      <div className={styles.sourceInfo}>
                        <ArrowRightLeft size={16} color="var(--accent-orange)" />
                        <div>
                          <div className={styles.sourceName}>{t.name}</div>
                          <div className={styles.sourceType}>
                            {ds.connection_type} • {ds.column_count} columns • Used in {ds.worksheets.length} sheets
                          </div>
                        </div>
                      </div>

                      {target ? (
                        <Badge status="COMPLETED" />
                      ) : (
                        <span
                          style={{
                            fontSize: "0.75rem",
                            padding: "0.15rem 0.5rem",
                            borderRadius: "4px",
                            background: "var(--accent-amber-muted)",
                            color: "var(--accent-amber)",
                            fontWeight: 600,
                          }}
                        >
                          NEEDS MAPPING
                        </span>
                      )}
                    </div>

                    {/* Mapping Target Box */}
                    <div className={styles.mappingBox}>
                      <Database size={16} color={target ? "var(--accent-cyan)" : "var(--text-tertiary)"} />
                      <span className={`${styles.targetText} ${!target ? styles.unmappedText : ""}`}>
                        {target || "No target Unity Catalog table selected"}
                      </span>

                      {sug?.matches?.[0] && !target && (
                        <span className={styles.suggestionBadge}>
                          <Sparkles size={12} />
                          {Math.round(sug.matches[0].confidence_score * 100)}% Match
                        </span>
                      )}
                    </div>

                    {/* Card Footer Actions */}
                    <div className={styles.cardActions}>
                      {sug?.matches?.[0] && !target && (
                        <Button
                          variant="secondary"
                          onClick={() => handleSelectTarget(t.name, sug.matches[0].target_full_name)}
                        >
                          Accept Suggestion ({sug.matches[0].target_full_name})
                        </Button>
                      )}

                      <Button
                        variant={isSelectedForMapping ? "primary" : "secondary"}
                        onClick={() => setActiveMappingTable(isSelectedForMapping ? null : t.name)}
                      >
                        {isSelectedForMapping ? "Selecting Target..." : target ? "Change Target" : "Select from Browser →"}
                      </Button>

                      <Button
                        variant="secondary"
                        onClick={() => {
                          setUploadTargetTable(t.clean_name || "imported_table");
                          setUploadModalOpen(true);
                        }}
                      >
                        Upload Table
                      </Button>
                    </div>
                  </div>
                );
              })
            )
          )}
        </div>

        {/* Right Column: Unity Catalog Tree Browser */}
        <div style={{ height: "100%" }}>
          <CatalogBrowser
            host={host}
            token={token}
            selectedTable={activeMappingTable ? mappings[activeMappingTable]?.target_full_name : undefined}
            onSelectTable={(fullName) => {
              if (activeMappingTable) {
                handleSelectTarget(activeMappingTable, fullName);
              } else {
                info("Select a datasource on the left first, then pick a target table here.", "Datasource Selection");
              }
            }}
          />
        </div>
      </div>

      {/* Bottom Bar: Progress & Gate */}
      <div className={styles.bottomBar}>
        <div className={styles.progressGroup}>
          <div className={styles.progressText}>
            Mapping Progress: {mappedCount} of {totalCount} datasources mapped
          </div>
          <div className={styles.progressBar}>
            <div className={styles.progressFill} style={{ width: `${progressPct}%` }} />
          </div>
        </div>

        <div style={{ display: "flex", gap: "0.75rem" }}>
          <Link href={`/migrations/${jobUuid}`}>
            <Button variant="secondary">Back to Workspace</Button>
          </Link>

          <Button
            variant="primary"
            icon={<ArrowRight size={16} />}
            disabled={!isComplete}
            onClick={handleSaveAndExecute}
          >
            Save & Execute Migration →
          </Button>
        </div>
      </div>

      {/* Upload Table Modal */}
      {uploadModalOpen && (
        <UploadTableModal
          defaultTableName={uploadTargetTable}
          onClose={() => setUploadModalOpen(false)}
          onSuccess={(fullName) => {
            if (activeMappingTable) {
              handleSelectTarget(activeMappingTable, fullName);
            }
            success(`Created and mapped table: ${fullName}`, "Table Uploaded");
          }}
        />
      )}
    </div>
  );
}
