"use client";

import { useState } from "react";
import { ChevronRight, ChevronDown, Database, LayoutDashboard, FileSpreadsheet, Calculator } from "lucide-react";
import { useSelectionStore } from "@/lib/store";
import styles from "./AssetTree.module.css";

interface AssetTreeProps {
  datasources?: string[];
  worksheets?: string[];
  dashboards?: string[];
}

export default function AssetTree({
  datasources = ["Orders", "Sales"],
  worksheets = ["Sales Trend", "Regional Summary"],
  dashboards = ["Executive Overview"],
}: AssetTreeProps) {
  const { selectAsset, selectedAssetId } = useSelectionStore();
  const [openDs, setOpenDs] = useState(true);
  const [openWs, setOpenWs] = useState(true);
  const [openDb, setOpenDb] = useState(true);

  return (
    <div className={styles.treeContainer}>
      <div className={styles.treeHeader}>Source Workbook Metadata</div>

      <div className={styles.treeContent}>
        {/* Datasources */}
        <div className={styles.groupItem}>
          <div className={styles.groupHeader} onClick={() => setOpenDs(!openDs)}>
            {openDs ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <Database size={14} color="var(--accent-blue)" />
            <span>Datasources ({datasources.length})</span>
          </div>
          {openDs && (
            <div className={styles.leafList}>
              {datasources.map((ds) => (
                <div
                  key={ds}
                  className={`${styles.leafItem} ${selectedAssetId === ds ? styles.selected : ""}`}
                  onClick={() => selectAsset("Datasource", ds)}
                >
                  ● {ds}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Worksheets */}
        <div className={styles.groupItem}>
          <div className={styles.groupHeader} onClick={() => setOpenWs(!openWs)}>
            {openWs ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <FileSpreadsheet size={14} color="var(--accent-purple)" />
            <span>Worksheets ({worksheets.length})</span>
          </div>
          {openWs && (
            <div className={styles.leafList}>
              {worksheets.map((ws) => (
                <div
                  key={ws}
                  className={`${styles.leafItem} ${selectedAssetId === ws ? styles.selected : ""}`}
                  onClick={() => selectAsset("Worksheet", ws)}
                >
                  ● {ws}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Dashboards */}
        <div className={styles.groupItem}>
          <div className={styles.groupHeader} onClick={() => setOpenDb(!openDb)}>
            {openDb ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <LayoutDashboard size={14} color="var(--accent-cyan)" />
            <span>Dashboards ({dashboards.length})</span>
          </div>
          {openDb && (
            <div className={styles.leafList}>
              {dashboards.map((db) => (
                <div
                  key={db}
                  className={`${styles.leafItem} ${selectedAssetId === db ? styles.selected : ""}`}
                  onClick={() => selectAsset("Dashboard", db)}
                >
                  ● {db}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
