"use client";

import { useState } from "react";
import { X, Sparkles, CheckCircle2, RefreshCw, ArrowRight } from "lucide-react";
import Button from "@/components/ui/Button";

interface QuickFixModalProps {
  isOpen: boolean;
  tier: string;
  issueDescription: string;
  suggestedFix: string;
  targetSqlBefore?: string;
  targetSqlAfter?: string;
  onApplyFix: () => void;
  onClose: () => void;
}

export default function QuickFixModal({
  isOpen,
  tier,
  issueDescription,
  suggestedFix,
  targetSqlBefore = "SELECT [Order Date], SUM([Sales]) FROM orders GROUP BY [Order Date]",
  targetSqlAfter = "SELECT EXTRACT(MONTH FROM Order_Date) AS Order_Date, SUM(Sales) AS Sales FROM orders GROUP BY 1",
  onApplyFix,
  onClose,
}: QuickFixModalProps) {
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);

  if (!isOpen) return null;

  const handleConfirm = () => {
    setApplying(true);
    setTimeout(() => {
      setApplying(false);
      setApplied(true);
      onApplyFix();
      setTimeout(() => {
        setApplied(false);
        onClose();
      }, 1000);
    }, 1200);
  };

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
          maxWidth: "620px",
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
              AI Quick Fix Remediation Workflow
            </h2>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer" }}
          >
            <X size={20} />
          </button>
        </div>

        {applied ? (
          <div style={{ padding: "2.5rem 1rem", textAlign: "center", color: "var(--accent-green)" }}>
            <CheckCircle2 size={48} style={{ marginBottom: "1rem" }} />
            <h3 style={{ fontSize: "1.25rem", color: "#fff", marginBottom: "0.5rem" }}>AI Remediation Applied Successfully!</h3>
            <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
              AST rules and Databricks Spark SQL queries updated and validated.
            </p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ padding: "0.75rem 1rem", borderRadius: "6px", background: "var(--bg-primary)", border: "1px solid var(--border-default)" }}>
              <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", textTransform: "uppercase" }}>Target Tier</span>
              <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--accent-orange)" }}>{tier}</div>
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>
                Detected Issue
              </label>
              <div style={{ padding: "0.75rem", background: "var(--bg-primary)", borderRadius: "6px", border: "1px solid var(--border-default)", fontSize: "0.875rem", color: "#fff" }}>
                {issueDescription}
              </div>
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>
                Proposed AI Remediation Fix
              </label>
              <div style={{ padding: "0.75rem", background: "rgba(46, 204, 113, 0.1)", borderRadius: "6px", border: "1px solid rgba(46, 204, 113, 0.3)", fontSize: "0.875rem", color: "var(--accent-green)" }}>
                {suggestedFix}
              </div>
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>
                AST Code Diff Comparison
              </label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--accent-red)", marginBottom: "0.25rem" }}>Before (Source AST)</div>
                  <pre className="mono" style={{ padding: "0.6rem", background: "var(--bg-primary)", border: "1px solid var(--border-default)", borderRadius: "6px", fontSize: "0.75rem", color: "var(--text-secondary)", margin: 0, whiteSpace: "pre-wrap" }}>
                    {targetSqlBefore}
                  </pre>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--accent-green)", marginBottom: "0.25rem" }}>After (Remediated AST)</div>
                  <pre className="mono" style={{ padding: "0.6rem", background: "var(--bg-primary)", border: "1px solid var(--border-default)", borderRadius: "6px", fontSize: "0.75rem", color: "var(--accent-green)", margin: 0, whiteSpace: "pre-wrap" }}>
                    {targetSqlAfter}
                  </pre>
                </div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "0.5rem" }}>
              <Button variant="secondary" onClick={onClose} disabled={applying}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleConfirm}
                disabled={applying}
                icon={applying ? <RefreshCw size={14} className="spin" /> : <Sparkles size={14} />}
              >
                {applying ? "Executing AI Fix..." : "Confirm & Apply Fix"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
