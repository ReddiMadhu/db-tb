"use client";

import { useState, useEffect } from "react";
import { Database, Search, Upload, Table, Layers } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import UploadModal from "@/components/migration/UploadModal";
import { listMigrationJobs } from "@/lib/api";

export default function DatasetsPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);

  useEffect(() => {
    listMigrationJobs()
      .then((data) => setJobs(data))
      .catch(() => setJobs([]))
      .finally(() => setLoading(false));
  }, []);

  const filteredJobs = jobs.filter((j) =>
    j.source_filename.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0 }}>Datasets Asset Browser</h1>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: "0.25rem 0 0" }}>
            Extracted datasources, join models, and transpiled Spark SQL datasets for Databricks Lakeview.
          </p>
        </div>

        <Button variant="primary" icon={<Upload size={16} />} onClick={() => setUploadOpen(true)}>
          New Migration
        </Button>
      </div>

      {/* Search Bar */}
      <div style={{ position: "relative" }}>
        <Search size={16} style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-tertiary)" }} />
        <input
          type="text"
          placeholder="Filter datasets by source workbook name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: "100%",
            padding: "0.6rem 0.8rem 0.6rem 2.4rem",
            background: "var(--bg-card)",
            border: "1px solid var(--border-default)",
            borderRadius: "6px",
            color: "#fff",
            fontSize: "0.875rem",
          }}
        />
      </div>

      {filteredJobs.length === 0 && !loading ? (
        <Card>
          <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
            <Database size={42} style={{ marginBottom: "1rem", opacity: 0.4 }} />
            <h3 style={{ color: "var(--text-primary)", marginBottom: "0.5rem" }}>No datasets available</h3>
            <p style={{ fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Upload a Tableau workbook (.twbx / .twb) to extract datasources and generate Databricks SQL queries.
            </p>
            <Button variant="primary" icon={<Upload size={16} />} onClick={() => setUploadOpen(true)}>
              Upload Workbook
            </Button>
          </div>
        </Card>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1rem" }}>
          {filteredJobs.map((j) => (
            <Card key={j.job_uuid}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <Database size={18} color="var(--accent-orange)" />
                  <strong style={{ fontSize: "1rem" }}>{j.source_filename}</strong>
                </div>
                <Badge status={j.status} />
              </div>

              <div style={{ padding: "0.75rem", borderRadius: "6px", background: "var(--bg-primary)", border: "1px solid var(--border-default)", marginBottom: "0.75rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
                  <span>Target Catalog:</span>
                  <span className="mono" style={{ color: "#fff" }}>main.default</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                  <span>SQL Transpiler Engine:</span>
                  <span className="mono" style={{ color: "var(--accent-green)" }}>Spark SQL 3.5</span>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                <span>Job: {j.job_uuid.slice(0, 8)}</span>
                <span style={{ color: "var(--accent-orange)", fontWeight: 600 }}>SQL Ready</span>
              </div>
            </Card>
          ))}
        </div>
      )}

      {uploadOpen && <UploadModal onClose={() => setUploadOpen(false)} />}
    </div>
  );
}
