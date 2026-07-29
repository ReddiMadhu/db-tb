"use client";

import { useState } from "react";
import { Activity, RefreshCw, CheckCircle2, Rocket, Upload, GitBranch, ShieldCheck } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Badge from "@/components/ui/Badge";

interface ActivityItem {
  id: string;
  timestamp: string;
  type: "UPLOAD" | "PARSED" | "VALIDATION" | "DEPLOYMENT";
  description: string;
  actor: string;
}

const INITIAL_ACTIVITIES: ActivityItem[] = [
  {
    id: "act-1",
    timestamp: "Just now",
    type: "VALIDATION",
    description: "Automated 6-Tier AST Validation passed with 100% schema compliance",
    actor: "LakeShift System",
  },
  {
    id: "act-2",
    timestamp: "15 mins ago",
    type: "DEPLOYMENT",
    description: "Target Databricks workspace connection verified for SQL Warehouse (a1b2c3d4e5f67890)",
    actor: "Enterprise Admin",
  },
  {
    id: "act-3",
    timestamp: "1 hour ago",
    type: "PARSED",
    description: "Tableau XML workbook reverse-engineering pipeline initialized",
    actor: "Pipeline Engine",
  },
];

export default function ActivityPage() {
  const [activities, setActivities] = useState<ActivityItem[]>(INITIAL_ACTIVITIES);
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = () => {
    setRefreshing(true);
    setTimeout(() => {
      setRefreshing(false);
    }, 800);
  };

  const getIcon = (type: ActivityItem["type"]) => {
    switch (type) {
      case "UPLOAD":
        return <Upload size={16} color="var(--accent-orange)" />;
      case "PARSED":
        return <GitBranch size={16} color="var(--accent-info)" />;
      case "VALIDATION":
        return <ShieldCheck size={16} color="var(--accent-green)" />;
      case "DEPLOYMENT":
        return <Rocket size={16} color="var(--accent-purple)" />;
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0 }}>Audit & Activity Feed</h1>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: "0.25rem 0 0" }}>
            Real-time security and operational event stream across all migration projects.
          </p>
        </div>

        <Button
          variant="secondary"
          disabled={refreshing}
          icon={<RefreshCw size={16} className={refreshing ? "spin" : ""} />}
          onClick={handleRefresh}
        >
          {refreshing ? "Refreshing..." : "Refresh Stream"}
        </Button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {activities.map((item) => (
          <Card key={item.id}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <div
                  style={{
                    padding: "0.5rem",
                    borderRadius: "6px",
                    background: "var(--bg-primary)",
                    border: "1px solid var(--border-default)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {getIcon(item.type)}
                </div>
                <div>
                  <strong style={{ fontSize: "0.95rem", color: "#fff", display: "block" }}>{item.description}</strong>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>Actor: {item.actor}</span>
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span className="mono" style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                  {item.timestamp}
                </span>
                <Badge status="COMPLETED" label={item.type} />
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
