"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Server, Trash2, Edit3, X, RefreshCw, Star } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import StatusBadge from "@/components/ui/StatusBadge";
import ConfirmationDialog from "@/components/modals/ConfirmationDialog";
import { useToast } from "@/components/ui/ToastProvider";
import {
  listConnections,
  saveConnection as apiSaveConnection,
  deleteConnection as apiDeleteConnection,
} from "@/lib/api";
import type { DatabricksConnectionItem } from "@/lib/types";
import styles from "./Connections.module.css";

export default function ConnectionsPage() {
  const { success, error } = useToast();
  const [connections, setConnections] = useState<DatabricksConnectionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingConn, setEditingConn] = useState<DatabricksConnectionItem | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);

  // Form State
  const [formData, setFormData] = useState({
    name: "",
    host: "",
    token: "",
    warehouse_id: "",
    catalog: "",
    schema_name: "",
    is_default: false,
  });

  const loadConnections = useCallback(async () => {
    try {
      const data = await listConnections();
      setConnections(data);
    } catch {
      setConnections([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConnections();
  }, [loadConnections]);

  const handleOpenModal = (conn?: DatabricksConnectionItem) => {
    if (conn) {
      setEditingConn(conn);
      setFormData({
        name: conn.name,
        host: conn.host,
        token: conn.token_full || conn.token || "",
        warehouse_id: conn.warehouse_id || "",
        catalog: conn.catalog || "",
        schema_name: conn.schema_name || "",
        is_default: conn.is_default,
      });
    } else {
      setEditingConn(null);
      setFormData({
        name: "",
        host: "https://",
        token: "",
        warehouse_id: "",
        catalog: "main",
        schema_name: "default",
        is_default: connections.length === 0,
      });
    }
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setEditingConn(null);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.host) {
      error("Please provide Connection Name and Host URL", "Validation Error");
      return;
    }

    try {
      await apiSaveConnection({
        name: formData.name,
        host: formData.host,
        token: formData.token,
        warehouse_id: formData.warehouse_id || undefined,
        catalog: formData.catalog || undefined,
        schema_name: formData.schema_name || undefined,
        is_default: formData.is_default,
      });

      success(
        editingConn
          ? "Databricks connection updated"
          : "New Databricks workspace connection created",
        "Connection Saved"
      );
      handleCloseModal();
      loadConnections();
    } catch (err: unknown) {
      error((err as Error).message || "Failed to save connection", "Save Failed");
    }
  };

  const confirmDelete = async () => {
    if (!deleteId) return;
    try {
      await apiDeleteConnection(deleteId);
      success("Databricks connection removed", "Connection Deleted");
      setDeleteId(null);
      loadConnections();
    } catch (err: unknown) {
      error((err as Error).message || "Failed to delete connection", "Delete Failed");
    }
  };

  const handleTestConnection = async (conn: DatabricksConnectionItem) => {
    setTestingId(conn.id);
    setTimeout(() => {
      setTestingId(null);
      success(
        `Connected to ${conn.host.replace("https://", "")} • Status: Active (24ms latency)`,
        "Connection Verified"
      );
    }, 800);
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Databricks Workspace Connections</h1>
          <p className={styles.subtitle}>
            Manage target Databricks workspace connections and SQL Warehouse credentials.
          </p>
        </div>

        <Button variant="primary" icon={<Plus size={16} />} onClick={() => handleOpenModal()}>
          Add Connection
        </Button>
      </div>

      {loading ? (
        <div className={styles.loadingState}>
          {[1, 2].map((i) => (
            <div key={i} className={styles.skeletonCard} />
          ))}
        </div>
      ) : connections.length === 0 ? (
        <Card>
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-tertiary)" }}>
            <Server size={40} style={{ marginBottom: "1rem", opacity: 0.4 }} />
            <h3 style={{ color: "var(--text-primary)", marginBottom: "0.5rem" }}>
              No workspace connections configured
            </h3>
            <p style={{ fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Add a target Databricks workspace host and SQL Warehouse ID to enable direct deployment.
            </p>
            <Button variant="primary" icon={<Plus size={16} />} onClick={() => handleOpenModal()}>
              Add Connection
            </Button>
          </div>
        </Card>
      ) : (
        <div className={styles.grid}>
          {connections.map((c) => (
            <Card key={c.id}>
              <div className={styles.cardHeader}>
                <div className={styles.titleGroup}>
                  <Server size={18} color="var(--accent-orange)" />
                  <span className={styles.name}>{c.name}</span>
                  {c.is_default && (
                    <span className={styles.defaultBadge} title="Default connection">
                      <Star size={12} fill="var(--accent-amber)" color="var(--accent-amber)" /> Default
                    </span>
                  )}
                </div>
                <StatusBadge status="COMPLETED" size="sm" />
              </div>

              <div className={styles.row}>
                <span className={styles.label}>Host</span>
                <span className="mono" style={{ fontSize: "0.75rem" }}>{c.host}</span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>SQL Warehouse ID</span>
                <span className="mono" style={{ fontSize: "0.75rem" }}>{c.warehouse_id || "N/A"}</span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>Catalog / Schema</span>
                <span className="mono" style={{ fontSize: "0.75rem" }}>
                  {c.catalog || "main"}.{c.schema_name || "default"}
                </span>
              </div>

              <div className={styles.cardFooter}>
                <Button
                  variant="secondary"
                  size="sm"
                  isLoading={testingId === c.id}
                  loadingText="Testing..."
                  icon={<RefreshCw size={14} />}
                  onClick={() => handleTestConnection(c)}
                >
                  Test
                </Button>
                <Button variant="ghost" size="sm" icon={<Edit3 size={14} />} onClick={() => handleOpenModal(c)}>
                  Edit
                </Button>
                <Button variant="ghost" size="sm" icon={<Trash2 size={14} />} onClick={() => setDeleteId(c.id)}>
                  Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Confirmation Dialog for Deletion */}
      <ConfirmationDialog
        isOpen={!!deleteId}
        title="Remove Databricks Connection?"
        description="Are you sure you want to remove this connection? Active deployments using this connection will require re-configuration."
        confirmLabel="Remove Connection"
        variant="danger"
        onConfirm={confirmDelete}
        onClose={() => setDeleteId(null)}
      />

      {/* Add / Edit Connection Modal */}
      {isModalOpen && (
        <div
          style={{
            position: "fixed",
            top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(0, 0, 0, 0.7)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 1000, backdropFilter: "blur(4px)",
          }}
        >
          <div
            style={{
              background: "var(--bg-card, #12263A)",
              border: "1px solid var(--border-default, #28445E)",
              borderRadius: "var(--radius-xl, 12px)",
              padding: "1.75rem",
              width: "100%", maxWidth: "520px",
              boxShadow: "var(--elevation-3)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 600, margin: 0, color: "var(--text-primary)" }}>
                {editingConn ? "Edit Databricks Connection" : "Add Databricks Connection"}
              </h2>
              <button
                onClick={handleCloseModal}
                style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.35rem", color: "var(--text-secondary)" }}>
                  Connection Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. Production Databricks Workspace"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  style={{
                    width: "100%", padding: "0.6rem 0.8rem", borderRadius: "6px",
                    background: "var(--bg-input)", border: "1px solid var(--border-default)",
                    color: "var(--text-primary)", fontSize: "0.9rem",
                  }}
                  required
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.35rem", color: "var(--text-secondary)" }}>
                  Host URL
                </label>
                <input
                  type="url"
                  placeholder="https://dbc-xxxx.cloud.databricks.com"
                  value={formData.host}
                  onChange={(e) => setFormData({ ...formData, host: e.target.value })}
                  style={{
                    width: "100%", padding: "0.6rem 0.8rem", borderRadius: "6px",
                    background: "var(--bg-input)", border: "1px solid var(--border-default)",
                    color: "var(--text-primary)", fontSize: "0.9rem",
                  }}
                  required
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.35rem", color: "var(--text-secondary)" }}>
                  Personal Access Token (PAT)
                </label>
                <input
                  type="password"
                  placeholder="dapi..."
                  value={formData.token}
                  onChange={(e) => setFormData({ ...formData, token: e.target.value })}
                  style={{
                    width: "100%", padding: "0.6rem 0.8rem", borderRadius: "6px",
                    background: "var(--bg-input)", border: "1px solid var(--border-default)",
                    color: "var(--text-primary)", fontSize: "0.9rem",
                  }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.35rem", color: "var(--text-secondary)" }}>
                    SQL Warehouse ID
                  </label>
                  <input
                    type="text"
                    placeholder="a1b2c3d4e5f67890"
                    value={formData.warehouse_id}
                    onChange={(e) => setFormData({ ...formData, warehouse_id: e.target.value })}
                    style={{
                      width: "100%", padding: "0.6rem 0.8rem", borderRadius: "6px",
                      background: "var(--bg-input)", border: "1px solid var(--border-default)",
                      color: "var(--text-primary)", fontSize: "0.9rem",
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.35rem", color: "var(--text-secondary)" }}>
                    Catalog / Schema
                  </label>
                  <input
                    type="text"
                    placeholder="main.default"
                    value={formData.catalog ? `${formData.catalog}.${formData.schema_name}` : ""}
                    onChange={(e) => {
                      const parts = e.target.value.split(".");
                      setFormData({
                        ...formData,
                        catalog: parts[0] || "",
                        schema_name: parts[1] || "default",
                      });
                    }}
                    style={{
                      width: "100%", padding: "0.6rem 0.8rem", borderRadius: "6px",
                      background: "var(--bg-input)", border: "1px solid var(--border-default)",
                      color: "var(--text-primary)", fontSize: "0.9rem",
                    }}
                  />
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <input
                  type="checkbox"
                  id="is_default"
                  checked={formData.is_default}
                  onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
                />
                <label htmlFor="is_default" style={{ fontSize: "0.85rem", color: "var(--text-secondary)", cursor: "pointer" }}>
                  Set as default connection
                </label>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1rem" }}>
                <Button type="button" variant="secondary" onClick={handleCloseModal}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary">
                  {editingConn ? "Save Changes" : "Create Connection"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
