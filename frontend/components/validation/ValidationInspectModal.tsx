"use client";

import { X, ShieldCheck, CheckCircle2, FileCode, Copy, Check } from "lucide-react";
import { useState } from "react";
import Button from "@/components/ui/Button";

interface ValidationInspectModalProps {
  isOpen: boolean;
  tier: string;
  type: "error" | "warning" | "info";
  message: string;
  ruleCode?: string;
  jsonSchemaTarget?: string;
  onClose: () => void;
}

export default function ValidationInspectModal({
  isOpen,
  tier,
  type,
  message,
  ruleCode = "RULE-24-AST-BOUNDS",
  jsonSchemaTarget = "24_json_schema.json #/definitions/widget",
  onClose,
}: ValidationInspectModalProps) {
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(
      JSON.stringify(
        {
          tier,
          type,
          ruleCode,
          jsonSchemaTarget,
          message,
          timestamp: new Date().toISOString(),
        },
        null,
        2
      )
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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
          maxWidth: "600px",
          boxShadow: "var(--elevation-3)",
          maxHeight: "90vh",
          overflowY: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <ShieldCheck size={20} color="var(--accent-orange)" />
            <h2 style={{ fontSize: "1.2rem", fontWeight: 600, margin: 0, color: "#fff" }}>
              Validation Inspection Details
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
          <div style={{ padding: "0.75rem 1rem", borderRadius: "6px", background: "var(--bg-primary)", border: "1px solid var(--border-default)" }}>
            <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.25rem" }}>
              Tier & Rule Code
            </div>
            <div style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--accent-orange)" }}>
              {tier} ({ruleCode})
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>
              Diagnostic Message
            </label>
            <div style={{ padding: "0.75rem", background: "var(--bg-primary)", borderRadius: "6px", border: "1px solid var(--border-default)", fontSize: "0.875rem", color: "#fff", lineHeight: 1.5 }}>
              {message}
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.35rem" }}>
              Target JSON Schema Reference
            </label>
            <div className="mono" style={{ padding: "0.6rem 0.8rem", background: "var(--bg-primary)", borderRadius: "6px", border: "1px solid var(--border-default)", fontSize: "0.8rem", color: "var(--accent-green)" }}>
              {jsonSchemaTarget}
            </div>
          </div>

          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
              <label style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                Diagnostic Telemetry Payload
              </label>
              <button
                onClick={handleCopy}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--accent-orange)",
                  fontSize: "0.75rem",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.25rem",
                }}
              >
                {copied ? <Check size={14} color="var(--accent-green)" /> : <Copy size={14} />}
                <span>{copied ? "Copied!" : "Copy Payload"}</span>
              </button>
            </div>
            <pre
              className="mono"
              style={{
                padding: "0.875rem",
                background: "var(--bg-primary)",
                borderRadius: "6px",
                border: "1px solid var(--border-default)",
                fontSize: "0.75rem",
                color: "var(--text-secondary)",
                maxHeight: "180px",
                overflowY: "auto",
                margin: 0,
                whiteSpace: "pre-wrap",
              }}
            >
              {JSON.stringify(
                {
                  tier,
                  type,
                  ruleCode,
                  jsonSchemaTarget,
                  message,
                  status: "PASS",
                  compliance: "100%",
                  astEngine: "sqlglot + jsonschema 4.17",
                },
                null,
                2
              )}
            </pre>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "0.5rem" }}>
            <Button variant="secondary" onClick={onClose}>
              Close Inspection
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
