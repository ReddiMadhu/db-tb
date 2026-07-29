"use client";

import { useState, useEffect } from "react";
import { Rocket, Server, CheckCircle2, Clock, Upload, ArrowUpRight } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import UploadModal from "@/components/migration/UploadModal";
import { listMigrationJobs } from "@/lib/api";

interface DeploymentItem {
  jobUuid: string;
  filename: string;
  environment: string;
  status: string;
  deployedAt: string;
  warehouseId: string;
}

export default function DeploymentsPage() {
  const [deployments, setDeployments] = useState<DeploymentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);

  useEffect(() => {
    listMigrationJobs()
      .then((jobs) => {
        const deployed = jobs
          .filter((j) => j.status === "DEPLOYED" || j.status === "COMPLETED")
          .map((j) => ({
            jobUuid: j.job_uuid,
            filename: j.source_filename,
            environment: "Production Workspace (AWS)",
            status: j.status === "DEPLOYED" ? "DEPLOYED" : "PARSED",
            deployedAt: j.completed_at || j.created_at || "Recently",
            warehouseId: "a1b2c3d4e5f67890",
          }));
        setDeployments(deployed);
      })
      .catch(() => setDeployments([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0 }}>Deployment History</h1>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: "0.25rem 0 0" }}>
            Track and publish Databricks AI/BI Lakeview asset bundles to target workspace SQL warehouses.
          </p>
        </div>

        <Button variant="primary" icon={<Upload size={16} />} onClick={() => setUploadOpen(true)}>
          New Deployment
        </Button>
      </div>

      {deployments.length === 0 && !loading ? (
        <Card>
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
            <Rocket size={42} style={{ marginBottom: "1rem", opacity: 0.4 }} />
            <h3 style={{ color: "var(--text-primary)", marginBottom: "0.5rem" }}>No active deployments found</h3>
            <p style={{ fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Upload and process a Tableau workbook to generate a Databricks Lakeview asset bundle ready for deployment.
            </p>
            <Button variant="primary" icon={<Upload size={16} />} onClick={() => setUploadOpen(true)}>
              Upload Workbook
            </Button>
          </div>
        </Card>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {deployments.map((d) => (
            <Card key={d.jobUuid}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                    <Server size={18} color="var(--accent-blue)" />
                    <strong style={{ fontSize: "1rem" }}>{d.filename}</strong>
                  </div>
                  <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0 }}>
                    Target: {d.environment} • Warehouse ID: <span className="mono">{d.warehouseId}</span> • Job UUID:{" "}
                    <span className="mono">{d.jobUuid.slice(0, 8)}</span>
                  </p>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <Badge status={d.status} label={d.status === "DEPLOYED" ? "Success" : "Ready"} />
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {uploadOpen && <UploadModal onClose={() => setUploadOpen(false)} />}
    </div>
  );
}
