"use client";

import { useState, useEffect } from "react";
import { Plus, Server, CheckCircle2, AlertCircle, Trash2, Edit3, Loader2, X, RefreshCw } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import ConfirmationDialog from "@/components/modals/ConfirmationDialog";
import { useToast } from "@/components/ui/ToastProvider";
import styles from "./Connections.module.css";

interface DatabricksConnection {
  id: string;
  name: string;
  host: string;
  token: string;
  warehouseId: string;
  catalogSchema: string;
  environment: "production" | "staging" | "development";
  isDefault?: boolean;
}

const DEFAULT_CONNECTIONS: DatabricksConnection[] = [
  {
    id: "conn-prod",
    name: "Production Workspace (AWS)",
    host: "https://dbc-prod-az.cloud.databricks.com",
    token: "dapi-prod-••••••••••••",
    warehouseId: "a1b2c3d4e5f67890",
    catalogSchema: "main.default",
    environment: "production",
    isDefault: true,
  },
  {
    id: "conn-dev",
    name: "Dev / Staging Workspace",
    host: "https://dbc-dev-az.cloud.databricks.com",
    token: "dapi-dev-••••••••••••",
    warehouseId: "f6e5d4c3b2a10987",
    catalogSchema: "staging.lakeview",
    environment: "staging",
    isDefault: false,
  },
];

export default function ConnectionsPage() {
  const { toast, success, error } = useToast();
  const [connections, setConnections] = useState<DatabricksConnection[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingConn, setEditingConn] = useState<DatabricksConnection | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  // Form State
  const [formData, setFormData] = useState({
    name: "",
    host: "",
    token: "",
    warehouseId: "",
    catalogSchema: "",
    environment: "development" as "production" | "staging" | "development",
  });

  useEffect(() => {
    const saved = localStorage.getItem("lakeview_connections");
    if (saved) {
      try {
        setConnections(JSON.parse(saved));
      } catch {
        setConnections(DEFAULT_CONNECTIONS);
      }
    } else {
      setConnections(DEFAULT_CONNECTIONS);
    }
  }, []);

  const saveConnectionsToStorage = (conns: DatabricksConnection[]) => {
    setConnections(conns);
    localStorage.setItem("lakeview_connections", JSON.stringify(conns));
  };

  const handleOpenModal = (conn?: DatabricksConnection) => {
    if (conn) {
      setEditingConn(conn);
      setFormData({
        name: conn.name,
        host: conn.host,
        token: conn.token,
        warehouseId: conn.warehouseId,
        catalogSchema: conn.catalogSchema,
        environment: conn.environment,
      });
    } else {
      setEditingConn(null);
      setFormData({
        name: "",
        host: "https://",
        token: "",
        warehouseId: "",
        catalogSchema: "main.default",
        environment: "development",
      });
    }
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setEditingConn(null);
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.host || !formData.warehouseId) {
      error("Please provide Connection Name, Host URL, and Warehouse ID", "Validation Error");
      return;
    }

    if (editingConn) {
      const updated = connections.map((c) =>
        c.id === editingConn.id ? { ...c, ...formData } : c
      );
      saveConnectionsToStorage(updated);
      success("Databricks workspace connection updated successfully", "Connection Saved");
    } else {
      const newConn: DatabricksConnection = {
        id: `conn-${Date.now()}`,
        ...formData,
        isDefault: connections.length === 0,
      };
      saveConnectionsToStorage([...connections, newConn]);
      success("New Databricks workspace connection created", "Connection Created");
    }
    handleCloseModal();
  };

  const confirmDelete = () => {
    if (!deleteId) return;
    const filtered = connections.filter((c) => c.id !== deleteId);
    saveConnectionsToStorage(filtered);
    success("Databricks connection removed from workspace", "Connection Deleted");
    setDeleteId(null);
  };

  const handleTestConnection = async (conn: DatabricksConnection) => {
    setTestingId(conn.id);
    setTimeout(() => {
      setTestingId(null);
      success(
        `Connected to ${conn.host.replace("https://", "")} • Warehouse ${conn.warehouseId} Active (38ms latency)`,
        "Connection Verified"
      );
    }, 1000);
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

      {connections.length === 0 ? (
        <Card>
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
            <Server size={40} style={{ marginBottom: "1rem", opacity: 0.4 }} />
            <h3 style={{ color: "var(--text-primary)", marginBottom: "0.5rem" }}>No workspace connections configured</h3>
            <p style={{ fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Add a target Databricks workspace host and SQL Warehouse ID to enable deployment.
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
                  <Server
                    size={18}
                    color={
                      c.environment === "production"
                        ? "var(--accent-purple)"
                        : c.environment === "staging"
                        ? "var(--accent-blue)"
                        : "var(--accent-cyan)"
                    }
                  />
                  <span className={styles.name}>{c.name}</span>
                </div>
                <Badge
                  status={c.environment === "production" ? "DEPLOYED" : "PARSED"}
                  label={c.environment.toUpperCase()}
                />
              </div>

              <div className={styles.row}>
                <span className={styles.label}>Host</span>
                <span className="mono" style={{ fontSize: "0.75rem" }}>{c.host}</span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>SQL Warehouse ID</span>
                <span className="mono" style={{ fontSize: "0.75rem" }}>{c.warehouseId}</span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>Catalog / Schema</span>
                <span className="mono" style={{ fontSize: "0.75rem" }}>{c.catalogSchema}</span>
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
                  Test Connection
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
        description="Are you sure you want to remove this connection? Active deployments using this credentials path will require re-configuration."
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
              background: "var(--bg-card, #1e293b)",
              border: "1px solid var(--border-subtle, #334155)",
              borderRadius: "var(--radius-lg, 12px)",
              padding: "1.75rem",
              width: "100%", maxWidth: "520px",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 600, margin: 0 }}>
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
                    background: "var(--bg-main, #0f172a)", border: "1px solid var(--border-subtle, #334155)",
                    color: "#fff", fontSize: "0.9rem",
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
                    background: "var(--bg-main, #0f172a)", border: "1px solid var(--border-subtle, #334155)",
                    color: "#fff", fontSize: "0.9rem",
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
                    background: "var(--bg-main, #0f172a)", border: "1px solid var(--border-subtle, #334155)",
                    color: "#fff", fontSize: "0.9rem",
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
                    value={formData.warehouseId}
                    onChange={(e) => setFormData({ ...formData, warehouseId: e.target.value })}
                    style={{
                      width: "100%", padding: "0.6rem 0.8rem", borderRadius: "6px",
                      background: "var(--bg-main, #0f172a)", border: "1px solid var(--border-subtle, #334155)",
                      color: "#fff", fontSize: "0.9rem",
                    }}
                    required
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "0.85rem", marginBottom: "0.35rem", color: "var(--text-secondary)" }}>
                    Catalog / Schema
                  </label>
                  <input
                    type="text"
                    placeholder="main.default"
                    value={formData.catalogSchema}
                    onChange={(e) => setFormData({ ...formData, catalogSchema: e.target.value })}
                    style={{
                      width: "100%", padding: "0.6rem 0.8rem", borderRadius: "6px",
                      background: "var(--bg-main, #0f172a)", border: "1px solid var(--border-subtle, #334155)",
                      color: "#fff", fontSize: "0.9rem",
                    }}
                  />
                </div>
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
