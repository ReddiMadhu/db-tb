"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Upload, ArrowRightLeft, ArrowRight, Layers } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import { SkeletonCard } from "@/components/ui/Skeleton";
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
          <h1 className={styles.title}>Migration Projects</h1>
          <p className={styles.subtitle}>Browse and manage active Tableau → Lakeview migration jobs.</p>
        </div>

        <Button variant="primary" icon={<Upload size={16} />} onClick={() => setUploadOpen(true)}>
          New Migration
        </Button>
      </div>

      {loading ? (
        <div className={styles.grid}>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : jobs.length === 0 ? (
        <Card>
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
            <Layers size={42} style={{ marginBottom: "1rem", opacity: 0.4 }} />
            <h3 style={{ color: "var(--text-primary)", marginBottom: "0.5rem" }}>No migration projects found</h3>
            <p style={{ fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Upload a Tableau workbook (.twbx / .twb) to create your first migration job.
            </p>
            <Button variant="primary" icon={<Upload size={16} />} onClick={() => setUploadOpen(true)}>
              New Migration
            </Button>
          </div>
        </Card>
      ) : (
        <div className={styles.grid}>
          {jobs.map((m) => (
            <Card key={m.job_uuid} clickable>
              <div className={styles.cardHeader}>
                <div className={styles.nameGroup}>
                  <ArrowRightLeft size={16} color="var(--accent-orange)" />
                  <span className={styles.name}>{m.source_filename}</span>
                </div>
                <Badge status={m.status} />
              </div>

              <div className={styles.details}>
                <span>Stage {m.current_stage}/10</span> • <span>UUID: {m.job_uuid.slice(0, 8)}</span>
              </div>

              <div className={styles.cardFooter}>
                <span>Status: {m.status}</span>
                <Link href={`/migrations/${m.job_uuid}`} className={styles.link}>
                  Open Workspace <ArrowRight size={14} />
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
