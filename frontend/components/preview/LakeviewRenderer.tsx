"use client";

import type { LakeviewDashboard } from "@/lib/types";
import { BarChart3, LineChart, Table, Hash, PieChart, Info, TrendingUp } from "lucide-react";
import { useSelectionStore } from "@/lib/store";
import styles from "./LakeviewRenderer.module.css";

interface LakeviewRendererProps {
  dashboard?: LakeviewDashboard | null;
}

const MOCK_PREVIEW_PAGES = [
  {
    displayName: "Executive Overview Dashboard",
    layout: [
      {
        widget: {
          name: "widget_kpi_revenue",
          spec: { widgetType: "counter", frame: { title: "Total Revenue ($)" } },
        },
        position: { width: 2, height: 2 },
      },
      {
        widget: {
          name: "widget_kpi_accounts",
          spec: { widgetType: "counter", frame: { title: "Active Accounts" } },
        },
        position: { width: 2, height: 2 },
      },
      {
        widget: {
          name: "widget_kpi_conversion",
          spec: { widgetType: "counter", frame: { title: "Conversion Rate" } },
        },
        position: { width: 2, height: 2 },
      },
      {
        widget: {
          name: "widget_bar_sales",
          spec: { widgetType: "bar", frame: { title: "Regional Sales Distribution" } },
        },
        position: { width: 3, height: 3 },
      },
      {
        widget: {
          name: "widget_line_trend",
          spec: { widgetType: "line", frame: { title: "Monthly Revenue Trajectory" } },
        },
        position: { width: 3, height: 3 },
      },
      {
        widget: {
          name: "widget_claims_table",
          spec: { widgetType: "table", frame: { title: "Claims Detail Record Table" } },
        },
        position: { width: 6, height: 4 },
      },
    ],
  },
];

// ── Widget Sub-Renderers ──

function CounterWidgetVisual({ title, name }: { title: string; name: string }) {
  const isRevenue = title.toLowerCase().includes("revenue") || name.includes("revenue");
  const isAccounts = title.toLowerCase().includes("account") || title.toLowerCase().includes("user");
  const val = isRevenue ? "$1,428,500" : isAccounts ? "12,840" : "94.2%";
  const growth = isRevenue ? "+14.2%" : "+8.7%";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", padding: "0.25rem 0" }}>
      <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#fff", letterSpacing: "-0.02em" }}>{val}</div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.75rem", color: "var(--accent-green)" }}>
        <TrendingUp size={14} />
        <span style={{ fontWeight: 600 }}>{growth}</span>
        <span style={{ color: "var(--text-tertiary)" }}>vs last month</span>
      </div>
    </div>
  );
}

function BarChartVisual() {
  const bars = [
    { label: "North America", val: 85, color: "var(--accent-orange)" },
    { label: "EMEA", val: 65, color: "var(--accent-green)" },
    { label: "APAC", val: 45, color: "var(--accent-info)" },
    { label: "LATAM", val: 30, color: "var(--accent-purple)" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", flex: 1, justifyContent: "center" }}>
      {bars.map((b) => (
        <div key={b.label} style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
            <span>{b.label}</span>
            <span className="mono">{b.val}%</span>
          </div>
          <div style={{ height: "8px", background: "var(--bg-tertiary)", borderRadius: "4px", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${b.val}%`, background: b.color, borderRadius: "4px" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function LineChartVisual() {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
      <svg width="100%" height="90" viewBox="0 0 300 90" preserveAspectRatio="none">
        <defs>
          <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#FB4E0B" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#FB4E0B" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        <path d="M 0,70 Q 50,20 100,40 T 200,30 T 300,10 L 300,90 L 0,90 Z" fill="url(#lineGrad)" />
        <path d="M 0,70 Q 50,20 100,40 T 200,30 T 300,10" fill="none" stroke="#FB4E0B" strokeWidth="2.5" />
        <circle cx="100" cy="40" r="4" fill="#FB4E0B" />
        <circle cx="200" cy="30" r="4" fill="#FB4E0B" />
        <circle cx="300" cy="10" r="4" fill="#FB4E0B" />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", width: "100%", fontSize: "0.7rem", color: "var(--text-tertiary)", marginTop: "0.25rem" }}>
        <span>Jan</span>
        <span>Mar</span>
        <span>May</span>
        <span>Jul</span>
        <span>Sep</span>
        <span>Nov</span>
      </div>
    </div>
  );
}

function TableWidgetVisual({ title }: { title: string }) {
  const rows = [
    { id: "CLM-9041", customer: "Acme Corp", region: "North America", amount: "$42,500", status: "Approved" },
    { id: "CLM-9042", customer: "Apex Global", region: "EMEA", amount: "$18,200", status: "Pending" },
    { id: "CLM-9043", customer: "Starlight Inc", region: "APAC", amount: "$94,100", status: "Approved" },
    { id: "CLM-9044", customer: "Vanguard Tech", region: "LATAM", amount: "$31,000", status: "Approved" },
  ];

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.75rem", textAlign: "left" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-default)", color: "var(--text-tertiary)", textTransform: "uppercase" }}>
              <th style={{ padding: "0.4rem 0.6rem" }}>Claim ID</th>
              <th style={{ padding: "0.4rem 0.6rem" }}>Customer</th>
              <th style={{ padding: "0.4rem 0.6rem" }}>Region</th>
              <th style={{ padding: "0.4rem 0.6rem" }}>Amount</th>
              <th style={{ padding: "0.4rem 0.6rem" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ borderBottom: "1px solid rgba(40, 68, 94, 0.4)", color: "var(--text-secondary)" }}>
                <td className="mono" style={{ padding: "0.45rem 0.6rem", color: "var(--accent-orange)" }}>{r.id}</td>
                <td style={{ padding: "0.45rem 0.6rem", color: "#fff" }}>{r.customer}</td>
                <td style={{ padding: "0.45rem 0.6rem" }}>{r.region}</td>
                <td className="mono" style={{ padding: "0.45rem 0.6rem", color: "#fff" }}>{r.amount}</td>
                <td style={{ padding: "0.45rem 0.6rem" }}>
                  <span style={{ padding: "1px 6px", borderRadius: "10px", fontSize: "0.7rem", background: r.status === "Approved" ? "rgba(46, 204, 113, 0.15)" : "rgba(245, 176, 65, 0.15)", color: r.status === "Approved" ? "var(--accent-green)" : "var(--accent-amber)" }}>
                    {r.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.7rem", color: "var(--text-tertiary)", marginTop: "auto" }}>
        <span>Databricks Lakeview Data Table • Showing 4 of 142 records</span>
        <span className="mono">Limit 1000</span>
      </div>
    </div>
  );
}

function PieChartVisual() {
  return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "space-around" }}>
      <svg width="80" height="80" viewBox="0 0 36 36">
        <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="var(--bg-tertiary)" strokeWidth="3.8" />
        <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#FB4E0B" strokeWidth="3.8" strokeDasharray="60, 100" />
        <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#2ECC71" strokeWidth="3.8" strokeDasharray="25, 100" strokeDashoffset="-60" />
        <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#3498DB" strokeWidth="3.8" strokeDasharray="15, 100" strokeDashoffset="-85" />
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.7rem", color: "var(--text-secondary)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
          <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#FB4E0B" }} />
          <span>Direct (60%)</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
          <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#2ECC71" }} />
          <span>Partner (25%)</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
          <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#3498DB" }} />
          <span>Organic (15%)</span>
        </div>
      </div>
    </div>
  );
}

// ── Main Component ──

export default function LakeviewRenderer({ dashboard }: LakeviewRendererProps) {
  const { selectAsset, selectedAssetId } = useSelectionStore();

  const pages = dashboard?.pages && dashboard.pages.length > 0 ? dashboard.pages : MOCK_PREVIEW_PAGES;
  const isSample = !dashboard || !dashboard.pages || dashboard.pages.length === 0;
  const page = pages[0];

  return (
    <div className={styles.previewContainer}>
      <div className={styles.pageHeader}>
        <div>
          <span className={styles.pageTitle}>{page.displayName || "Dashboard Page"}</span>
          {isSample && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", marginLeft: "0.75rem", fontSize: "0.75rem", color: "var(--accent-orange)", background: "rgba(251, 78, 11, 0.12)", padding: "2px 8px", borderRadius: "12px" }}>
              <Info size={12} /> Template Preview (Run Pipeline to generate live AST)
            </span>
          )}
        </div>
        <span style={{ fontSize: "var(--font-size-xs)", color: "var(--text-tertiary)" }}>
          Databricks Lakeview Canvas • 6-Column Grid • {page.layout.length} Widgets
        </span>
      </div>

      <div className={styles.grid}>
        {page.layout.map((item, idx) => {
          const w = item.widget;
          const pos = item.position;
          const title = (w.spec?.frame as { title?: string })?.title || `Widget ${idx + 1}`;
          const widgetType = ((w.spec?.widgetType as string) || "table").toLowerCase();

          const isSelected = selectedAssetId === w.name;

          let Icon = Table;
          if (widgetType === "bar") Icon = BarChart3;
          else if (widgetType === "line") Icon = LineChart;
          else if (widgetType === "counter" || widgetType === "kpi") Icon = Hash;
          else if (widgetType === "pie") Icon = PieChart;

          return (
            <div
              key={w.name || idx}
              className={`${styles.widget} ${isSelected ? styles.selected : ""}`}
              style={{
                gridColumn: `span ${Math.min(6, Math.max(1, pos.width))}`,
                minHeight: `${Math.max(120, pos.height * 55)}px`,
              }}
              onClick={() => selectAsset("Widget", w.name || `widget_${idx}`)}
            >
              <div className={styles.widgetTitle}>
                <span className="truncate" style={{ fontWeight: 600, color: "#fff" }}>
                  {title}
                </span>
                <Icon size={14} color="var(--accent-orange)" />
              </div>

              {/* Visual Sub-Renderers */}
              {widgetType === "counter" || widgetType === "kpi" ? (
                <CounterWidgetVisual title={title} name={w.name} />
              ) : widgetType === "bar" ? (
                <BarChartVisual />
              ) : widgetType === "line" ? (
                <LineChartVisual />
              ) : widgetType === "pie" ? (
                <PieChartVisual />
              ) : (
                <TableWidgetVisual title={title} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
