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
}

export default function RelationshipDiagram({ joins }: RelationshipDiagramProps) {
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
        {joins.map((j, idx) => (
          <div
            key={`${j.left_table}-${j.right_table}-${idx}`}
            className={styles.joinRow}
            style={{ animationDelay: `${idx * 40}ms` }}
          >
            <div className={styles.tableBox}>
              {j.left_table}
              <span className={styles.columnName}>.{j.left_column}</span>
            </div>
            <div className={styles.arrow}>
              <ArrowRight size={14} />
            </div>
            <div className={styles.tableBox}>
              {j.right_table}
              <span className={styles.columnName}>.{j.right_column}</span>
            </div>
            {j.join_type && (
              <span className={styles.joinType}>{j.join_type}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
