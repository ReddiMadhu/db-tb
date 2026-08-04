"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, RefreshCw, BarChart2, PieChart, LineChart, Table2, MapPin, Filter, Gauge } from "lucide-react";
import type { VisualCompatibilityItem } from "@/lib/types";
import styles from "./VisualCompatibilityMatrix.module.css";

interface VisualCompatibilityMatrixProps {
  items?: VisualCompatibilityItem[];
}

export default function VisualCompatibilityMatrix({ items = [] }: VisualCompatibilityMatrixProps) {
  const defaultItems: VisualCompatibilityItem[] = [
    { visual: "Bar Chart", status: "COMPATIBLE", notes: "Mapped to Lakeview Bar Spec" },
    { visual: "Line Chart", status: "COMPATIBLE", notes: "Mapped to Lakeview Line Spec" },
    { visual: "Pie Chart", status: "COMPATIBLE", notes: "Mapped to Lakeview Pie Spec" },
    { visual: "Table Grid", status: "COMPATIBLE", notes: "Mapped to Lakeview Table Widget" },
    { visual: "KPI Metric Cards", status: "COMPATIBLE", notes: "Mapped to Counter Metric Card" },
    { visual: "Interactive Filters", status: "COMPATIBLE", notes: "Mapped to Dashboard Filter Controls" },
    { visual: "Parameters", status: "CONVERTED", notes: "Converted to Lakeview Dashboard Parameters" },
    { visual: "Map Visualizations", status: "UNSUPPORTED", notes: "Converted to Geographical Table Grid" },
  ];

  const list = items.length > 0 ? items : defaultItems;

  const getIcon = (name: string) => {
    const n = name.toLowerCase();
    if (n.includes("bar")) return <BarChart2 size={16} />;
    if (n.includes("line")) return <LineChart size={16} />;
    if (n.includes("pie")) return <PieChart size={16} />;
    if (n.includes("table")) return <Table2 size={16} />;
    if (n.includes("map")) return <MapPin size={16} />;
    if (n.includes("filter")) return <Filter size={16} />;
    return <Gauge size={16} />;
  };

  return (
    <div className={styles.matrixGrid}>
      {list.map((item, idx) => {
        const isComp = item.status === "COMPATIBLE";
        const isConv = item.status === "CONVERTED";
        const tagClass = isComp ? styles.tagCompatible : isConv ? styles.tagConverted : styles.tagUnsupported;

        return (
          <div key={idx} className={styles.itemCard}>
            <div>
              <div className={styles.visualName}>
                <span style={{ color: "var(--accent-cyan)" }}>{getIcon(item.visual)}</span>
                {item.visual}
              </div>
              {item.notes && <div className={styles.notes}>{item.notes}</div>}
            </div>

            <span className={`${styles.statusTag} ${tagClass}`}>
              {isComp ? (
                <>
                  <CheckCircle2 size={12} /> Compatible
                </>
              ) : isConv ? (
                <>
                  <RefreshCw size={12} /> Converted
                </>
              ) : (
                <>
                  <AlertTriangle size={12} /> Unsupported
                </>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}
