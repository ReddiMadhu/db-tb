"use client";

import { useState } from "react";
import { Activity, RefreshCw, CheckCircle2, Rocket, Upload, GitBranch, ShieldCheck, BarChart2, Cpu } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";
import StructuredLogViewer from "@/components/activity/StructuredLogViewer";
import { useToast } from "@/components/ui/ToastProvider";

export default function ActivityPage() {
  const { success } = useToast();
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = () => {
    setRefreshing(true);
    setTimeout(() => {
      setRefreshing(false);
      success("Activity stream & observability metrics refreshed", "Stream Refreshed");
    }, 600);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0 }}>System Observability & Audit Logs</h1>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: "0.25rem 0 0" }}>
            Real-time security events, pipeline execution logs, correlation IDs, and telemetry metrics.
          </p>
        </div>

        <Button
          variant="secondary"
          isLoading={refreshing}
          loadingText="Refreshing..."
          icon={<RefreshCw size={16} />}
          onClick={handleRefresh}
        >
          Refresh Stream
        </Button>
      </div>

      {/* Observability Dashboard KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1rem" }}>
        <Card>
          <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>Migrations Today</div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "#fff" }}>14 Jobs</div>
          <div style={{ fontSize: "0.75rem", color: "var(--accent-green)" }}>100% Success Rate</div>
        </Card>

        <Card>
          <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>Avg Pipeline Runtime</div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--accent-green)" }}>1.38s</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>10-stage automated AST compilation</div>
        </Card>

        <Card>
          <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>Failed SQL Transpilation</div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--accent-green)" }}>0 Errors</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>sqlglot AST transpiler</div>
        </Card>

        <Card>
          <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>LLM Token Usage</div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--accent-purple)" }}>1,240 Tokens</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Azure OpenAI gpt-4o fallback</div>
        </Card>
      </div>

      {/* Searchable Structured Logs */}
      <div>
        <h2 style={{ fontSize: "1.1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1rem" }}>
          Structured Log Event Stream
        </h2>
        <StructuredLogViewer />
      </div>
    </div>
  );
}
