"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Upload, FileSpreadsheet, AlertCircle } from "lucide-react";
import Button from "@/components/ui/Button";
import { useToast } from "@/components/ui/ToastProvider";
import { uploadWorkbook } from "@/lib/api";
import styles from "./UploadModal.module.css";

interface UploadModalProps {
  onClose: () => void;
}

export default function UploadModal({ onClose }: UploadModalProps) {
  const router = useRouter();
  const { success, error: toastError } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      if (!selected.name.endsWith(".twb") && !selected.name.endsWith(".twbx")) {
        setError("Invalid file type. Please select a valid Tableau Workbook file (.twb or .twbx)");
        setFile(null);
        return;
      }
      setFile(selected);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);

    try {
      const res = await uploadWorkbook(file);
      success(`Workbook "${file.name}" uploaded & XML TOM metadata extracted`, "Upload Complete");
      onClose();
      router.push(`/migrations/${res.job_uuid}`);
    } catch (err: unknown) {
      const msg = (err as Error).message || "Upload failed";
      setError(msg);
      toastError(msg, "Upload Failed");
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
            disabled={!file}
            isLoading={uploading}
            loadingText="Parsing Metadata..."
            icon={<FileSpreadsheet size={14} />}
          >
            Upload & Parse
          </Button>
        </div>
      </div>
    </div>
  );
}
