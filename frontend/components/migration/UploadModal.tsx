"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Upload, FileSpreadsheet, Loader2, AlertCircle } from "lucide-react";
import Button from "@/components/ui/Button";
import { uploadWorkbook } from "@/lib/api";
import styles from "./UploadModal.module.css";

interface UploadModalProps {
  onClose: () => void;
}

export default function UploadModal({ onClose }: UploadModalProps) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);

    try {
      const res = await uploadWorkbook(file);
      onClose();
      router.push(`/migrations/${res.job_uuid}`);
    } catch (err: unknown) {
      setError((err as Error).message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.title}>Upload Tableau Workbook</div>

        <label className={styles.dropZone}>
          <input
            type="file"
            accept=".twb,.twbx"
            className={styles.fileInput}
            onChange={handleFileChange}
          />
          <Upload size={32} color="var(--accent-orange)" />
          <div className={styles.dropText}>
            {file ? (
              <strong style={{ color: "var(--accent-green)" }}>{file.name}</strong>
            ) : (
              <>
                <strong>Click to browse</strong> or drag and drop
                <br />
                Supports Tableau Workbook files (.twb, .twbx)
              </>
            )}
          </div>
        </label>

        {error && (
          <div style={{ color: "var(--accent-red)", fontSize: "var(--font-size-xs)", display: "flex", alignItems: "center", gap: "0.35rem", marginTop: "0.5rem" }}>
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        )}

        <div className={styles.actions}>
          <Button variant="ghost" onClick={onClose} disabled={uploading}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleUpload}
            disabled={!file || uploading}
            icon={uploading ? <Loader2 size={14} className="spin" /> : <FileSpreadsheet size={14} />}
          >
            {uploading ? "Parsing Metadata..." : "Upload & Parse"}
          </Button>
        </div>
      </div>
    </div>
  );
}
