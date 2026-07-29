"use client";

import { useState, useEffect } from "react";
import { BookOpen, Upload } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import UploadModal from "@/components/migration/UploadModal";
import { listMigrationJobs } from "@/lib/api";

interface JobItem {
  id: number;
  job_uuid: string;
  source_filename: string;
  status: string;
  current_stage: number;
}

export default function WorkbooksPage() {
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);

  useEffect(() => {
    listMigrationJobs()
      .then((data) => setJobs(data))
      .catch(() => setJobs([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0 }}>Workbooks Asset Browser</h1>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: "0.25rem 0 0" }}>
            Cross-cutting search across all uploaded Tableau workbooks and parsed XML structures.
          </p>
        </div>

        <Button variant="primary" icon={<Upload size={16} />} onClick={() => setUploadOpen(true)}>
          Upload Workbook
        </Button>
      </div>

      {jobs.length === 0 && !loading ? (
        <Card>
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
            <BookOpen size={42} style={{ marginBottom: "1rem", opacity: 0.4 }} />
            <h3 style={{ color: "var(--text-primary)", marginBottom: "0.5rem" }}>No workbooks indexed</h3>
            <p style={{ fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Upload a Tableau workbook (.twbx / .twb) to inspect parsed worksheets and datasources.
            </p>
            <Button variant="primary" icon={<Upload size={16} />} onClick={() => setUploadOpen(true)}>
              Upload Workbook
            </Button>
          </div>
        </Card>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "1rem" }}>
          {jobs.map((j) => (
            <Card key={j.job_uuid}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                <strong style={{ fontSize: "1rem" }}>{j.source_filename}</strong>
                <Badge status={j.status} />
              </div>
              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0 }}>
                Stage {j.current_stage}/10 • UUID: <span className="mono">{j.job_uuid.slice(0, 8)}</span>
              </p>
            </Card>
          ))}
        </div>
      )}

      {uploadOpen && <UploadModal onClose={() => setUploadOpen(false)} />}
    </div>
  );
}
