"use client";

import React, { useState } from "react";
import { LayoutGrid, Filter, BarChart3, TrendingUp, PieChart, Database, Sparkles } from "lucide-react";
import styles from "./DashboardVisualPreview.module.css";

interface DashboardVisualPreviewProps {
  dashboardName?: string;
  pages?: Array<{
    name: string;
    display_name?: string;
    widgets?: Array<{
      name: string;
      type?: string;
      visual_type?: string;
      position?: { x: number; y: number; w: number; h: number };
    }>;
  }>;
}

export default function DashboardVisualPreview({
  dashboardName = "Insurance Claims Performance",
  pages = [],
}: DashboardVisualPreviewProps) {
  const [activePageIdx, setActivePageIdx] = useState(0);

  const displayPages = pages.length > 0 ? pages : [
    {
      name: "overview",
      display_name: "Claims Executive Summary",
      widgets: [
        { name: "Total Claims Volume", type: "KPI", visual_type: "counter", position: { x: 0, y: 0, w: 2, h: 2 } },
        { name: "Approved Claim Rate", type: "KPI", visual_type: "counter", position: { x: 2, y: 0, w: 2, h: 2 } },
        { name: "Avg Settlement Days", type: "KPI", visual_type: "counter", position: { x: 4, y: 0, w: 2, h: 2 } },
        { name: "Monthly Claim Trend by Region", type: "Chart", visual_type: "bar", position: { x: 0, y: 2, w: 4, h: 4 } },
        { name: "Claims Breakdown by Category", type: "Chart", visual_type: "pie", position: { x: 4, y: 2, w: 2, h: 4 } },
      ]
    }
  ];

  const currentPage = displayPages[activePageIdx] || displayPages[0];

  return (
    <div className={styles.container}>
      <div className={styles.headerBar}>
        <div className={styles.dashboardTitle}>
          <LayoutGrid size={18} style={{ color: "var(--accent-cyan)" }} />
          {dashboardName}
        </div>
        <div className={styles.badgeGroup}>
          <span className={`${styles.tag} ${styles.tagActive}`}>
            <Sparkles size={11} style={{ display: "inline", marginRight: 4 }} />
            Responsive 6-Column Grid
          </span>
          <span className={styles.tag}>Databricks Lakeview AST</span>
        </div>
      </div>

      {/* Pages Tab Bar if multiple pages */}
      {displayPages.length > 1 && (
        <div style={{ display: "flex", gap: "0.5rem", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.5rem" }}>
          {displayPages.map((p, idx) => (
            <button
              key={idx}
              className={`${styles.tag} ${activePageIdx === idx ? styles.tagActive : ""}`}
              onClick={() => setActivePageIdx(idx)}
              style={{ cursor: "pointer" }}
            >
              {p.display_name || p.name}
            </button>
          ))}
        </div>
      )}

      {/* Filter Bar Mock */}
      <div className={styles.filterBar}>
        <span className={styles.filterLabel}>
          <Filter size={12} /> Interactive Filters:
        </span>
        <span className={styles.filterPill}>Region: All Regions</span>
        <span className={styles.filterPill}>Date Range: YTD</span>
        <span className={styles.filterPill}>Policy Type: Commercial</span>
      </div>

      {/* 6-Column Layout Grid */}
      <div className={styles.gridContainer}>
        {currentPage.widgets?.map((w, idx) => {
          const spanClass = w.position?.w === 6 ? styles.span6 : w.position?.w === 4 ? styles.span4 : w.position?.w === 3 ? styles.span3 : styles.span2;
          const isKpi = w.type === "KPI" || w.visual_type === "counter" || w.position?.w === 2;

          return (
            <div key={idx} className={`${styles.widgetCard} ${spanClass}`}>
              <div className={styles.widgetHeader}>
                <span className={styles.widgetName}>{w.name}</span>
                <span className={styles.widgetType}>
                  {w.visual_type ? w.visual_type.toUpperCase() : w.type || "WIDGET"}
                </span>
              </div>

              {isKpi ? (
                <div>
                  <div className={styles.kpiValue}>
                    {idx === 0 ? "142,850" : idx === 1 ? "94.2%" : "4.2 Days"}
                  </div>
                  <div className={styles.kpiTrend}>
                    <TrendingUp size={12} /> +8.4% vs prev quarter
                  </div>
                </div>
              ) : w.visual_type === "pie" ? (
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: "60px" }}>
                  <PieChart size={40} style={{ color: "var(--accent-purple)", opacity: 0.8 }} />
                  <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                    <div>■ Auto: 45%</div>
                    <div>■ Property: 35%</div>
                    <div>■ Life: 20%</div>
                  </div>
                </div>
              ) : (
                <div className={styles.chartMock}>
                  <div className={styles.bar} style={{ height: "40%" }} />
                  <div className={styles.bar} style={{ height: "65%" }} />
                  <div className={styles.bar} style={{ height: "90%" }} />
                  <div className={styles.bar} style={{ height: "75%" }} />
                  <div className={styles.bar} style={{ height: "55%" }} />
                  <div className={styles.bar} style={{ height: "85%" }} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
