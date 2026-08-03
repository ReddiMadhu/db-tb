"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRightLeft,
  Upload,
  LayoutDashboard,
  FileUp,
  ExternalLink,
  Trash2,
} from "lucide-react";
import KpiCard from "@/components/ui/KpiCard";
import StatusBadge from "@/components/ui/StatusBadge";
import UploadModal from "@/components/migration/UploadModal";
import { listMigrationJobs } from "@/lib/api";
import styles from "./Home.module.css";

interface JobRow {
  id: number;
  job_uuid: string;
  source_filename: string;
  status: string;
  current_stage: number;
  created_at: string | null;
  completed_at: string | null;
}

export default function DashboardPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);

  const fetchJobs = useCallback(async () => {
    try {
      const data = await listMigrationJobs();
      setJobs(data);
    } catch (e) {
      console.error("Failed to fetch jobs:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // KPI calculations
  const totalWorkbooks = jobs.length;
  const deployedCount = jobs.filter(
    (j) => j.status === "DEPLOYED" || j.status === "COMPLETED"
  ).length;

  return (
    <div className={styles.page}>
      {/* Page Header */}
      <div className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>Dashboard</h1>
          <p className={styles.pageSubtitle}>
            Tableau to Databricks AI/BI migration overview
          </p>
        </div>
        <button
          className={styles.uploadBtn}
          onClick={() => setUploadOpen(true)}
        >
          <FileUp size={18} />
          Start Migration
        </button>
      </div>

      {/* KPI Cards */}
      <div className={styles.kpiRow}>
        <KpiCard
          value={totalWorkbooks}
          label="Workbooks Processed"
          icon={<LayoutDashboard size={28} />}
          accentColor="var(--accent-orange)"
          loading={loading}
        />
        <KpiCard
          value={deployedCount}
          label="Dashboards Deployed"
          icon={<ArrowRightLeft size={28} />}
          accentColor="var(--accent-green)"
          loading={loading}
        />
      </div>

      {/* Recent Migrations Table */}
      <div className={styles.tableSection}>
        <h2 className={styles.sectionTitle}>Recent Migrations</h2>

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
            <p>Upload a Tableau workbook (.twbx) to begin your first migration.</p>
            <button
              className={styles.emptyUploadBtn}
              onClick={() => setUploadOpen(true)}
            >
              <FileUp size={16} />
              Upload Workbook
            </button>
          </div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Status</th>
                  <th>Stages</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr
                    key={job.job_uuid}
                    className={styles.tableRow}
                    onClick={() =>
                      router.push(`/migrations/${job.job_uuid}`)
                    }
                  >
                    <td className={styles.filenameCell}>
                      <span className={styles.filename}>
                        {job.source_filename}
                      </span>
                    </td>
                    <td>
                      <StatusBadge status={job.status} />
                    </td>
                    <td className={styles.stageCell}>
                      {job.current_stage}/9
                    </td>
                    <td className={styles.dateCell}>
                      {job.created_at
                        ? new Date(job.created_at).toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
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
                        title="Open migration"
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
      </div>

      {/* Upload Modal */}
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
