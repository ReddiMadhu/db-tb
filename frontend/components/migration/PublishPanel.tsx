"use client";

import { useState, useEffect } from "react";
import { Rocket, RefreshCw, CheckCircle2, ExternalLink } from "lucide-react";
import { useToast } from "@/components/ui/ToastProvider";
import { deployToDatabricks, listConnections } from "@/lib/api";
import styles from "./PublishPanel.module.css";

interface PublishPanelProps {
  jobUuid: string;
  initialArtifacts?: Record<string, any>;
  onPublished?: () => void;
}

export default function PublishPanel({ jobUuid, initialArtifacts = {}, onPublished }: PublishPanelProps) {
  const { success, error: toastError } = useToast();
  const [publishing, setPublishing] = useState(false);
  const [publishedResult, setPublishedResult] = useState<{
    dashboard_id?: string;
    published_url?: string;
  } | null>(
    initialArtifacts.dashboard_id
      ? { dashboard_id: initialArtifacts.dashboard_id, published_url: initialArtifacts.published_url }
      : null
  );

  const [host, setHost] = useState("");
  const [token, setToken] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [catalog, setCatalog] = useState("");
  const [schemaName, setSchemaName] = useState("");
  const [hasSavedToken, setHasSavedToken] = useState(false);
  const [savedConnectionName, setSavedConnectionName] = useState<string | null>(null);

  useEffect(() => {
    async function initConnection() {
      try {
        const conns = await listConnections();
        if (conns && conns.length > 0) {
          const def = conns.find((c) => c.is_default) || conns[0];
          setHost(def.host || "");
          // Do not pre-fill the PAT into the browser — server resolves it.
          const tok = Boolean(def.has_token || def.token_full || def.token);
          setHasSavedToken(tok);
          setSavedConnectionName(def.name || null);
          setToken("");
          if (def.warehouse_id) setWarehouseId(def.warehouse_id);
          if (def.catalog) setCatalog(def.catalog);
          if (def.schema_name) setSchemaName(def.schema_name);
          return;
        }
      } catch {}

      const saved = localStorage.getItem("lakeview_connections");
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          if (parsed.length > 0) {
            setHost(parsed[0].host || "");
            const tok = Boolean(parsed[0].token_full || parsed[0].token);
            setHasSavedToken(tok);
            setToken("");
            setWarehouseId(parsed[0].warehouseId || "");
            setCatalog(parsed[0].catalog || "");
            setSchemaName(parsed[0].schema || "");
          }
        } catch {}
      }
    }
    initConnection();
  }, []);

  const handlePublish = async () => {
    setPublishing(true);
    try {
      // Omit empty fields so the server can resolve from the saved connection
      const res = await deployToDatabricks(jobUuid, {
        warehouse_id: warehouseId || undefined,
        host: host || undefined,
        // Only send an override PAT; otherwise the server uses the saved connection
        token: token || undefined,
        catalog: catalog || undefined,
        schema_name: schemaName || undefined,
      });

      setPublishedResult({
        dashboard_id: res.dashboard_id,
        published_url: res.published_url,
      });
      success(`Dashboard published successfully! ID: ${res.dashboard_id}`, "Published");
      onPublished?.();
    } catch (err: any) {
      toastError(err.message || "Failed to publish dashboard to Databricks.", "Deployment Failed");
    } finally {
      setPublishing(false);
    }
  };

  if (publishedResult) {
    return (
      <div className={styles.successCard}>
        <div className={styles.successHeader}>
          <CheckCircle2 size={22} /> Dashboard Published to Databricks
        </div>
        <div className={styles.successDetail}>
          Dashboard ID: <strong>{publishedResult.dashboard_id}</strong>
        </div>
        {publishedResult.published_url ? (
          <a
            href={publishedResult.published_url}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.openLinkBtn}
          >
            Open Published Dashboard in Databricks <ExternalLink size={14} />
          </a>
        ) : (
          <button className={styles.publishBtn} onClick={() => setPublishedResult(null)}>
            Re-Publish Dashboard
          </button>
        )}
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.iconBox}>
          <Rocket size={20} />
        </div>
        <div>
          <div className={styles.title}>Publish to Databricks SQL Warehouse</div>
          <div className={styles.desc}>
            Deploy the transpiled Lakeview JSON dashboard directly into your Databricks workspace via REST API.
            {hasSavedToken && savedConnectionName
              ? ` Using saved connection "${savedConnectionName}" for credentials.`
              : ""}
          </div>
        </div>
      </div>

      <div className={styles.grid}>
        <div className={styles.formGroup}>
          <label className={styles.label}>
            SQL Warehouse ID{hasSavedToken ? " (optional — uses saved connection)" : " *"}
          </label>
          <input
            type="text"
            className={styles.input}
            placeholder="e.g. a1b2c3d4e5f67890"
            value={warehouseId}
            onChange={(e) => setWarehouseId(e.target.value)}
          />
        </div>

        <div className={styles.formGroup}>
          <label className={styles.label}>Databricks Host (Optional)</label>
          <input
            type="text"
            className={styles.input}
            placeholder="https://adb-xxxx.azuredatabricks.net"
            value={host}
            onChange={(e) => setHost(e.target.value)}
          />
        </div>

        <div className={styles.formGroup}>
          <label className={styles.label}>
            Personal Access Token (PAT)
            {hasSavedToken ? " — optional override" : ""}
          </label>
          <input
            type="password"
            className={styles.input}
            placeholder={
              hasSavedToken
                ? "Leave blank to use saved connection PAT"
                : "dapi..."
            }
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </div>

        <div className={styles.formGroup}>
          <label className={styles.label}>Target Catalog (Optional)</label>
          <input
            type="text"
            className={styles.input}
            placeholder="e.g. main"
            value={catalog}
            onChange={(e) => setCatalog(e.target.value)}
          />
        </div>
      </div>

      <button className={styles.publishBtn} onClick={handlePublish} disabled={publishing}>
        {publishing ? <RefreshCw size={18} className="spin" /> : <Rocket size={18} />}
        {publishing ? "Publishing to Databricks..." : "Publish to Databricks Workspace"}
      </button>
    </div>
  );
}
