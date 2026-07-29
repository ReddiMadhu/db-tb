"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Upload, ArrowRight, Layers } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import Skeleton, { SkeletonCard } from "@/components/ui/Skeleton";
import UploadModal from "@/components/migration/UploadModal";
import { listMigrationJobs } from "@/lib/api";
import styles from "./Home.module.css";

interface MigrationJobItem {
  id: number;
  job_uuid: string;
  source_filename: string;
  status: string;
  current_stage: number;
  created_at: string | null;
  completed_at: string | null;
}

export default function HomePage() {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [jobs, setJobs] = useState<MigrationJobItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listMigrationJobs()
      .then((data) => {
        setJobs(data);
      })
      .catch(() => {
        setJobs([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const totalJobs = jobs.length;
  const completedJobs = jobs.filter((j) => j.status === "COMPLETED" || j.status === "DEPLOYED").length;

  return (
    <div className={styles.container}>
      {/* Hero Welcome Banner */}
      <div className={styles.hero}>
        <div>
          <h1 className={styles.title}>Welcome to LakeShift</h1>
          <p className={styles.subtitle}>
            Enterprise control plane for migrating Tableau dashboards to Databricks AI/BI (Lakeview).
          </p>
        </div>
        <div className={styles.heroActions}>
          <Button variant="primary" icon={<Upload size={16} />} onClick={() => setUploadOpen(true)}>
            Upload Workbook (.twbx)
          </Button>
        </div>
      </div>

      {/* Stats KPI Row */}
      <div className={styles.statsGrid}>
        <Card>
          <div className={styles.statLabel}>Total Migrations</div>
          <div className={styles.statValue}>{loading ? <Skeleton width="48px" height="32px" /> : totalJobs}</div>
          <div className={styles.statSub}>{totalJobs} workbooks indexed</div>
        </Card>
        <Card>
          <div className={styles.statLabel}>Completed Jobs</div>
          <div className={styles.statValue} style={{ color: "var(--accent-green)" }}>
            {loading ? <Skeleton width="48px" height="32px" /> : completedJobs}
          </div>
          <div className={styles.statSub}>{completedJobs} successfully processed</div>
        </Card>
        <Card>
          <div className={styles.statLabel}>Deployments</div>
          <div className={styles.statValue} style={{ color: "var(--accent-info)" }}>
            {loading ? <Skeleton width="48px" height="32px" /> : jobs.filter((j) => j.status === "DEPLOYED").length}
          </div>
          <div className={styles.statSub}>Databricks AI/BI Lakeview</div>
        </Card>
      </div>

      {/* Quick Access Migrations */}
      <div className={styles.sectionHeader}>
        <h2>Recent Migration Projects</h2>
        <Link href="/migrations" style={{ color: "var(--accent-orange)", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: "0.25rem" }}>
          View All <ArrowRight size={14} />
        </Link>
      </div>

      {loading ? (
        <div className={styles.projectsGrid}>
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : jobs.length === 0 ? (
        <Card>
          <div style={{ padding: "2.5rem", textAlign: "center", color: "var(--text-muted)" }}>
            <Layers size={36} style={{ marginBottom: "0.75rem", opacity: 0.5 }} />
            <h3 style={{ color: "var(--text-primary)", marginBottom: "0.5rem" }}>No active migration projects</h3>
            <p style={{ fontSize: "0.875rem", marginBottom: "1.25rem" }}>
              Upload a Tableau workbook (.twbx / .twb) to initiate the automated migration pipeline.
            </p>
            <Button variant="primary" icon={<Upload size={16} />} onClick={() => setUploadOpen(true)}>
              Upload Workbook (.twbx)
            </Button>
          </div>
        </Card>
      ) : (
        <div className={styles.projectsGrid}>
          {jobs.slice(0, 4).map((j) => (
            <Card key={j.job_uuid} clickable>
              <div className={styles.projectHeader}>
                <span className={styles.projectName}>{j.source_filename}</span>
                <Badge status={j.status} />
              </div>
              <p className={styles.projectDesc}>Stage {j.current_stage}/10 • Job ID: {j.job_uuid.slice(0, 8)}</p>
              <div className={styles.projectFooter}>
                <span>Status: {j.status}</span>
                <Link href={`/migrations/${j.job_uuid}`} className={styles.openBtn}>
                  Inspect <ArrowRight size={14} />
                </Link>
              </div>
            </Card>
          ))}
        </div>
      )}

      {uploadOpen && <UploadModal onClose={() => setUploadOpen(false)} />}
    </div>
  );
}
