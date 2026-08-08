"use client";

import React from "react";
import { ArrowRight } from "lucide-react";
import styles from "./RelationshipDiagram.module.css";

export interface JoinRelation {
  join_type?: string;
  left_table: string;
  left_column: string;
  right_table: string;
  right_column: string;
  datasource?: string;
}

interface RelationshipDiagramProps {
  joins: JoinRelation[];
  activeTable?: string | null;
}

export default function RelationshipDiagram({ joins, activeTable }: RelationshipDiagramProps) {
  if (!joins || joins.length === 0) {
    return (
      <div className={styles.empty}>
        No table relationships detected in this workbook.
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.title}>
        Detected Relationships ({joins.length})
      </div>
      <div className={styles.diagram}>
        {joins.map((j, idx) => {
          const isConnected =
            Boolean(activeTable) &&
            (j.left_table.toLowerCase() === activeTable?.toLowerCase() ||
              j.right_table.toLowerCase() === activeTable?.toLowerCase());

          return (
            <div
              key={`${j.left_table}-${j.right_table}-${idx}`}
              className={`${styles.joinRow} ${isConnected ? styles.joinRowActive : ""}`}
              style={{ animationDelay: `${idx * 40}ms` }}
            >
              <div
                className={`${styles.tableBox} ${
                  activeTable && j.left_table.toLowerCase() === activeTable.toLowerCase()
                    ? styles.tableBoxActive
                    : ""
                }`}
              >
                {j.left_table}
                <span className={styles.columnName}>.{j.left_column}</span>
              </div>
              <div className={`${styles.arrow} ${isConnected ? styles.arrowActive : ""}`}>
                <ArrowRight size={14} />
              </div>
              <div
                className={`${styles.tableBox} ${
                  activeTable && j.right_table.toLowerCase() === activeTable.toLowerCase()
                    ? styles.tableBoxActive
                    : ""
                }`}
              >
                {j.right_table}
                <span className={styles.columnName}>.{j.right_column}</span>
              </div>
              {j.join_type && (
                <span className={`${styles.joinType} ${isConnected ? styles.joinTypeActive : ""}`}>
                  {j.join_type}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

