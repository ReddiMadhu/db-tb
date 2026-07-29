"use client";

import { useState } from "react";
import { Upload, X, FileSpreadsheet, Loader2, CheckCircle2 } from "lucide-react";
import Button from "@/components/ui/Button";
import styles from "./UploadTableModal.module.css";

interface UploadTableModalProps {
  defaultCatalog?: string;
  defaultSchema?: string;
  defaultTableName?: string;
  onClose: () => void;
  onSuccess: (fullName: string) => void;
}

export default function UploadTableModal({
  defaultCatalog = "main",
  defaultSchema = "default",
  defaultTableName = "imported_table",
  onClose,
  onSuccess,
}: UploadTableModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [catalog, setCatalog] = useState(defaultCatalog);
  const [schemaName, setSchemaName] = useState(defaultSchema);
  const [tableName, setTableName] = useState(defaultTableName);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      setFile(selected);
      // Clean filename for default table name
      const base = selected.name.split(".")[0].toLowerCase().replace(/[^a-z0-9_]/g, "_");
      setTableName(base);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const selected = e.dataTransfer.files[0];
      setFile(selected);
      const base = selected.name.split(".")[0].toLowerCase().replace(/[^a-z0-9_]/g, "_");
      setTableName(base);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Please select a file to upload.");
      return;
    }
    if (!catalog || !schemaName || !tableName) {
      setError("Please fill in catalog, schema, and table name.");
      return;
    }

    setUploading(true);
    setError(null);

    try {
      // Simulate upload completion or call upload API
      const fullName = `${catalog}.${schemaName}.${tableName}`;
      setTimeout(() => {
        onSuccess(fullName);
        onClose();
      }, 1000);
    } catch (err: any) {
      setError(err.message || "Failed to upload table.");
      setUploading(false);
    }
  };

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <div className={styles.title}>
            <Upload size={18} color="var(--accent-orange)" />
            Upload Table to Unity Catalog
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* Dropzone */}
          <div
            className={`${styles.dropzone} ${dragging ? styles.dropzoneActive : ""}`}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => document.getElementById("table-file-input")?.click()}
          >
            <input
              id="table-file-input"
              type="file"
              accept=".csv,.xlsx,.xls,.parquet"
              style={{ display: "none" }}
              onChange={handleFileChange}
            />
            {file ? (
              <>
                <FileSpreadsheet size={32} color="var(--accent-green)" />
                <span className={styles.dropzoneText} style={{ color: "#fff", fontWeight: 600 }}>
                  {file.name}
                </span>
                <span className={styles.dropzoneSubtext}>
                  {(file.size / 1024).toFixed(1)} KB • Click to change file
                </span>
              </>
            ) : (
              <>
                <Upload size={32} color="var(--accent-orange)" />
                <span className={styles.dropzoneText}>
                  Drag & drop CSV, Excel, or Parquet file here
                </span>
                <span className={styles.dropzoneSubtext}>or click to browse files</span>
              </>
            )}
          </div>

          {/* Form Fields */}
          <div className={styles.formGrid}>
            <div>
              <label className={styles.label}>Catalog</label>
              <input
                type="text"
                className={styles.input}
                value={catalog}
                onChange={(e) => setCatalog(e.target.value)}
                required
              />
            </div>
            <div>
              <label className={styles.label}>Schema</label>
              <input
                type="text"
                className={styles.input}
                value={schemaName}
                onChange={(e) => setSchemaName(e.target.value)}
                required
              />
            </div>
          </div>

          <div>
            <label className={styles.label}>Table Name</label>
            <input
              type="text"
              className={styles.input}
              value={tableName}
              onChange={(e) => setTableName(e.target.value)}
              required
            />
          </div>

          {error && (
            <div style={{ color: "var(--accent-red)", fontSize: "0.8125rem" }}>
              {error}
            </div>
          )}

          <div className={styles.footer}>
            <Button type="button" variant="secondary" onClick={onClose} disabled={uploading}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={uploading || !file}>
              {uploading ? (
                <>
                  <Loader2 size={16} className="spin" />
                  Creating Table...
                </>
              ) : (
                "Upload & Map Table"
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
