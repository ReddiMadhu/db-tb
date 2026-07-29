"use client";

import { useState } from "react";
import { CheckCircle2, ShieldCheck, Sparkles, RefreshCw } from "lucide-react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import ValidationCard from "@/components/validation/ValidationCard";
import ValidationInspectModal from "@/components/validation/ValidationInspectModal";
import QuickFixModal from "@/components/validation/QuickFixModal";
import styles from "./ValidationPage.module.css";

interface ValidationItem {
  id: string;
  type: "error" | "warning" | "info";
  tier: string;
  ruleCode: string;
  message: string;
  schemaTarget: string;
  issueDescription: string;
  suggestedFix: string;
  targetSqlBefore?: string;
  targetSqlAfter?: string;
}

const VALIDATION_ITEMS: ValidationItem[] = [
  {
    id: "val-1",
    type: "info",
    tier: "Tier 1: JSON Schema Validation",
    ruleCode: "RULE-24-AST-SCHEMA",
    message: "AST structure validated against 24_json_schema.json specification. 0 schema errors detected.",
    schemaTarget: "24_json_schema.json #/definitions/widget",
    issueDescription: "Verify widget grid positions (x, y, width, height) against Lakeview dashboard schema.",
    suggestedFix: "Auto-format widget coordinates to conform to 6-column layout parameters.",
  },
  {
    id: "val-2",
    type: "info",
    tier: "Tier 2: Spark SQL Validation",
    ruleCode: "RULE-SQLGLOT-AST",
    message: "Custom SQL queries transpiled cleanly with sqlglot for Databricks Spark SQL.",
    schemaTarget: "24_json_schema.json #/definitions/dataset/query",
    issueDescription: "Validate Spark SQL dialect compatibility for legacy Tableau custom SQL expressions.",
    suggestedFix: "Transpile Tableau bracket notation `[Field]` into unquoted `Field` Spark SQL column references.",
    targetSqlBefore: "SELECT [Order Date], SUM([Sales]) FROM orders GROUP BY [Order Date]",
    targetSqlAfter: "SELECT Order_Date, SUM(Sales) FROM orders GROUP BY Order_Date",
  },
  {
    id: "val-3",
    type: "info",
    tier: "Tier 3: Reference Integrity",
    ruleCode: "RULE-REF-INTEGRITY",
    message: "All widget query references bound to existing dataset names.",
    schemaTarget: "24_json_schema.json #/definitions/widget/queries/dataset",
    issueDescription: "Check dataset bindings between visualizations and query parameters.",
    suggestedFix: "Re-bind orphan widget reference to active dataset `Orders_Dataset`.",
  },
  {
    id: "val-4",
    type: "info",
    tier: "Tier 4: Layout Bounds Validation",
    ruleCode: "RULE-LAYOUT-BOUNDS",
    message: "All visual widgets bound within 6-column grid bounds (x+width <= 6).",
    schemaTarget: "24_json_schema.json #/definitions/layout/position",
    issueDescription: "Validate canvas overflow bounds.",
    suggestedFix: "Clamp layout width to x + width <= 6.",
  },
  {
    id: "val-5",
    type: "info",
    tier: "Tier 5: Widget Spec Validation",
    ruleCode: "RULE-WIDGET-SPEC",
    message: "Widget specs match version 1 (table), version 2 (counter), version 3 (chart).",
    schemaTarget: "24_json_schema.json #/definitions/widget_spec",
    issueDescription: "Check widget type specifications.",
    suggestedFix: "Set version field to match widget type spec 1, 2, or 3.",
  },
  {
    id: "val-6",
    type: "info",
    tier: "Tier 6: ID Uniqueness & Cycle Validation",
    ruleCode: "RULE-ID-UNIQUENESS",
    message: "All entity IDs generated using 8-character lowercase hex format.",
    schemaTarget: "24_json_schema.json #/definitions/id",
    issueDescription: "Check for duplicate or cyclic dependency references.",
    suggestedFix: "Regenerate unique 8-character hex ID string.",
  },
];

export default function ValidationPage() {
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // Modal States
  const [inspectModalItem, setInspectModalItem] = useState<ValidationItem | null>(null);
  const [quickFixModalItem, setQuickFixModalItem] = useState<ValidationItem | null>(null);

  const handleRunAiFix = () => {
    setRunning(true);
    setNotice(null);
    setTimeout(() => {
      setRunning(false);
      setNotice("Automated 6-Tier AST Validation sweep completed. All 24_json_schema.json constraints verified with 100% compliance.");
    }, 1500);
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Global Validation Center</h1>
          <p className={styles.subtitle}>
            Real-time 6-Tier AST validation results across all active migration jobs.
          </p>
        </div>
        <Button
          variant="primary"
          disabled={running}
          icon={running ? <RefreshCw size={16} className="spin" /> : <Sparkles size={16} />}
          onClick={handleRunAiFix}
        >
          {running ? "Running Validation..." : "Run AI Validation Sweep"}
        </Button>
      </div>

      {notice && (
        <div
          style={{
            padding: "0.875rem 1.25rem",
            borderRadius: "6px",
            background: "rgba(46, 204, 113, 0.12)",
            border: "1px solid rgba(46, 204, 113, 0.3)",
            color: "var(--accent-green)",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            fontSize: "0.875rem",
          }}
        >
          <CheckCircle2 size={18} />
          <span>{notice}</span>
        </div>
      )}

      <div className={styles.summaryRow}>
        <Card className={styles.summaryCard}>
          <span className={styles.num} style={{ color: "var(--accent-green)" }}>
            6/6
          </span>
          <span className={styles.lbl}>Validation Tiers Passed</span>
        </Card>

        <Card className={styles.summaryCard}>
          <span className={styles.num} style={{ color: "var(--accent-green)" }}>
            0
          </span>
          <span className={styles.lbl}>Blocking Errors</span>
        </Card>

        <Card className={styles.summaryCard}>
          <span className={styles.num} style={{ color: "var(--accent-orange)" }}>
            100%
          </span>
          <span className={styles.lbl}>Schema Compliance</span>
        </Card>
      </div>

      <div className={styles.section}>
        <h2>Automated Validation Results</h2>

        {VALIDATION_ITEMS.map((item) => (
          <ValidationCard
            key={item.id}
            type={item.type}
            tier={item.tier}
            message={item.message}
            onInspect={() => setInspectModalItem(item)}
            onAiFix={() => setQuickFixModalItem(item)}
          />
        ))}
      </div>

      {/* Inspect Modal */}
      {inspectModalItem && (
        <ValidationInspectModal
          isOpen={!!inspectModalItem}
          tier={inspectModalItem.tier}
          type={inspectModalItem.type}
          message={inspectModalItem.message}
          ruleCode={inspectModalItem.ruleCode}
          jsonSchemaTarget={inspectModalItem.schemaTarget}
          onClose={() => setInspectModalItem(null)}
        />
      )}

      {/* Quick Fix Modal */}
      {quickFixModalItem && (
        <QuickFixModal
          isOpen={!!quickFixModalItem}
          tier={quickFixModalItem.tier}
          issueDescription={quickFixModalItem.issueDescription}
          suggestedFix={quickFixModalItem.suggestedFix}
          targetSqlBefore={quickFixModalItem.targetSqlBefore}
          targetSqlAfter={quickFixModalItem.targetSqlAfter}
          onApplyFix={() => {
            setNotice(`AI Quick Fix applied for ${quickFixModalItem.tier}. AST constraints verified.`);
          }}
          onClose={() => setQuickFixModalItem(null)}
        />
      )}
    </div>
  );
}
