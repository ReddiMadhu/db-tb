"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Upload, ExternalLink, Trash2, FileUp } from "lucide-react";
import StatusBadge from "@/components/ui/StatusBadge";
import UploadModal from "@/components/migration/UploadModal";
import { listMigrationJobs } from "@/lib/api";
import styles from "./Migrations.module.css";

interface MigrationJobItem {
  id: number;
  job_uuid: string;
  source_filename: string;
  status: string;
  current_stage: number;
  created_at: string | null;
  completed_at: string | null;
}

export default function MigrationsPage() {
  const router = useRouter();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [jobs, setJobs] = useState<MigrationJobItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listMigrationJobs()
      .then((data) => setJobs(data))
      .catch(() => setJobs([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Migrations</h1>
          <p className={styles.subtitle}>
            Browse and manage active Tableau → Databricks migration jobs.
          </p>
        </div>
        <button
          className={styles.uploadBtn}
          onClick={() => setUploadOpen(true)}
        >
          <FileUp size={16} />
          Upload Workbook
        </button>
      </div>

      {loading ? (
        <div className={styles.loadingState}>
          {[1, 2, 3].map((i) => (
            <div key={i} className={styles.skeletonRow} />
          ))}
        </div>
      ) : jobs.length === 0 ? (
        <div className={styles.emptyState}>
          <Upload size={48} strokeWidth={1} />
          <h3>No migrations yet</h3>
          <p>Upload a Tableau workbook to create your first migration.</p>
          <button
            className={styles.emptyUploadBtn}
            onClick={() => setUploadOpen(true)}
          >
            <FileUp size={16} />
            Upload Workbook
          </button>
        </div>
      ) : (
        <div className={styles.tableCard}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Filename</th>
                <th>Status</th>
                <th>Stages</th>
                <th>Created</th>
                <th>Completed</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr
                  key={job.job_uuid}
                  className={styles.tableRow}
                  onClick={() => router.push(`/migrations/${job.job_uuid}`)}
                >
                  <td className={styles.filenameCell}>
                    <span className={styles.filename}>{job.source_filename}</span>
                    <span className={styles.uuid}>{job.job_uuid}</span>
                  </td>
                  <td>
                    <StatusBadge status={job.status} />
                  </td>
                  <td className={styles.monoCell}>{job.current_stage}/9</td>
                  <td className={styles.dateCell}>
                    {job.created_at
                      ? new Date(job.created_at).toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "—"}
                  </td>
                  <td className={styles.dateCell}>
                    {job.completed_at
                      ? new Date(job.completed_at).toLocaleDateString("en-US", {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "—"}
                  </td>
                  <td>
                    <button
                      className={styles.actionBtn}
                      onClick={(e) => {
                        e.stopPropagation();
                        router.push(`/migrations/${job.job_uuid}`);
                      }}
                      title="Open workspace"
                    >
                      <ExternalLink size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {uploadOpen && (
        <UploadModal
          onClose={() => setUploadOpen(false)}
          onSuccess={(jobUuid) => {
            setUploadOpen(false);
            router.push(`/migrations/${jobUuid}`);
          }}
        />
      )}
    </div>
  );
}
