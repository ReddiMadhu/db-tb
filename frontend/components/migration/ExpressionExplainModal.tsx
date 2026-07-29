"use client";

import { X, Sparkles, CheckCircle2 } from "lucide-react";
import Button from "@/components/ui/Button";

interface ExpressionExplainModalProps {
  isOpen: boolean;
  name: string;
  type: string;
  sourceFormula: string;
  targetSql: string;
  confidence: number;
  method: string;
  onClose: () => void;
}

export default function ExpressionExplainModal({
  isOpen,
  name,
  type,
  sourceFormula,
  targetSql,
  confidence,
  method,
  onClose,
}: ExpressionExplainModalProps) {
  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.75)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--bg-card, #12263a)",
          border: "1px solid var(--border-default, #28445e)",
          borderRadius: "var(--radius-xl, 12px)",
          padding: "1.75rem",
          width: "100%",
          maxWidth: "580px",
          boxShadow: "var(--elevation-3)",
          maxHeight: "90vh",
          overflowY: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Sparkles size={20} color="var(--accent-orange)" />
            <h2 style={{ fontSize: "1.2rem", fontWeight: 600, margin: 0, color: "#fff" }}>
              AI Calculated Field Translation Analysis
            </h2>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}
          >
            <X size={20} />
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div style={{ padding: "0.75rem 1rem", borderRadius: "6px", background: "var(--bg-primary)", border: "1px solid var(--border-default)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", textTransform: "uppercase" }}>Field Name & Category</div>
              <div style={{ fontSize: "1rem", fontWeight: 600, color: "#fff" }}>{name}</div>
            </div>
            <span style={{ padding: "2px 8px", borderRadius: "12px", background: "rgba(251, 78, 11, 0.15)", color: "var(--accent-orange)", fontSize: "0.75rem", fontWeight: 600 }}>
              {type}
            </span>
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>
              Source Tableau Expression
            </label>
            <pre className="mono" style={{ padding: "0.75rem", background: "var(--bg-primary)", borderRadius: "6px", border: "1px solid var(--border-default)", fontSize: "0.8rem", color: "#fff", margin: 0, whiteSpace: "pre-wrap" }}>
              {sourceFormula}
            </pre>
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>
              Target Databricks Spark SQL AST
            </label>
            <pre className="mono" style={{ padding: "0.75rem", background: "var(--bg-primary)", borderRadius: "6px", border: "1px solid var(--border-default)", fontSize: "0.8rem", color: "var(--accent-green)", margin: 0, whiteSpace: "pre-wrap" }}>
              {targetSql}
            </pre>
          </div>

          <div style={{ padding: "0.875rem", background: "var(--bg-primary)", borderRadius: "6px", border: "1px solid var(--border-default)" }}>
            <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--accent-orange)", marginBottom: "0.35rem" }}>
              Compiler Analysis & Partition Breakdown
            </div>
            <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.5 }}>
              The Tableau <code>{type}</code> expression was transpiled using the {method}. Partition specifications were mapped to ANSI SQL window frames (<code>OVER (PARTITION BY ...)</code>) with {confidence}% rule confidence.
            </p>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "0.5rem" }}>
            <Button variant="secondary" onClick={onClose}>
              Close Explanation
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
