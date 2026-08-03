"use client";

import { useState, useEffect } from "react";
import { ChevronDown, ChevronUp, Download, Clock } from "lucide-react";
import { getStageConfig } from "@/lib/pipeline.config";
import { getStageDetail } from "@/lib/api";
import StatusBadge from "@/components/ui/StatusBadge";
import type { StageDetail } from "@/lib/types";
import styles from "./StageDetailPanel.module.css";

interface StageDetailPanelProps {
  jobUuid: string;
  stageId: string;
  isComplete?: boolean;      // pipeline overall complete
  onDownload?: () => void;   // download handler for Finalize stage
}

export default function StageDetailPanel({
  jobUuid,
  stageId,
  isComplete,
  onDownload,
}: StageDetailPanelProps) {
  const [detail, setDetail] = useState<StageDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(["metrics", "details"])
  );

  const config = getStageConfig(stageId);

  useEffect(() => {
    setLoading(true);
    getStageDetail(jobUuid, stageId)
      .then((d) => setDetail(d))
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [jobUuid, stageId]);

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) next.delete(section);
      else next.add(section);
      return next;
    });
  };

  if (loading) {
    return (
      <div className={styles.panel}>
        <div className={styles.skeleton} />
        <div className={styles.skeleton} style={{ width: "60%" }} />
        <div className={styles.skeleton} style={{ width: "80%" }} />
      </div>
    );
  }

  if (!config) return null;

  const status = detail?.status || "WAITING";
  const metrics = detail?.metrics || {};
  const isWaiting = status === "WAITING";

  // Group detail fields by section
  const metricFields = config.detailFields.filter((f) => f.section === "metrics");
  const detailFieldsList = config.detailFields.filter((f) => f.section === "details");

  return (
    <div className={styles.panel} style={{ animationDelay: "0ms" }}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h2 className={styles.title}>{config.title}</h2>
          <p className={styles.description}>{config.description}</p>
        </div>
        <div className={styles.headerRight}>
          <StatusBadge status={status} size="md" />
          {detail?.duration_ms != null && (
            <span className={styles.duration}>
              <Clock size={13} />
              {detail.duration_ms}ms
            </span>
          )}
        </div>
      </div>

      {isWaiting ? (
        <div className={styles.waitingState}>
          <p>This stage has not been executed yet.</p>
          <p className={styles.waitingHint}>
            Data will be populated after pipeline execution.
          </p>
        </div>
      ) : (
        <>
          {/* Summaries */}
          {(detail?.input_summary || detail?.output_summary) && (
            <div className={styles.summaryRow}>
              {detail.input_summary && (
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>Input</span>
                  <span className={styles.summaryValue}>{detail.input_summary}</span>
                </div>
              )}
              {detail.output_summary && (
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>Output</span>
                  <span className={styles.summaryValueGreen}>{detail.output_summary}</span>
                </div>
              )}
            </div>
          )}

          {/* Mini KPI Badges */}
          {metricFields.length > 0 && (
            <div className={styles.kpiBadges}>
              {metricFields.map((field, i) => {
                const val = metrics[field.key];
                if (val === undefined || val === null) return null;
                return (
                  <div key={field.key} className={styles.kpiBadge} style={{ animationDelay: `${i * 60}ms` }}>
                    <span className={styles.kpiValue}>
                      {typeof val === "boolean" ? (val ? "✓" : "✗") : String(val)}
                    </span>
                    <span className={styles.kpiLabel}>{field.label}</span>
                  </div>
                );
              })}
            </div>
          )}

          {/* Details Section */}
          {detailFieldsList.length > 0 && Object.keys(metrics).length > 0 && (
            <div className={styles.section}>
              <button
                className={styles.sectionHeader}
                onClick={() => toggleSection("details")}
              >
                <span>Details</span>
                {expandedSections.has("details") ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
              {expandedSections.has("details") && (
                <div className={styles.sectionBody}>
                  <div className={styles.detailGrid}>
                    {detailFieldsList.map((field) => {
                      const val = metrics[field.key];
                      if (val === undefined || val === null) return null;
                      return (
                        <div key={field.key} className={styles.detailRow}>
                          <span className={styles.detailLabel}>{field.label}</span>
                          <span className={styles.detailValue}>
                            {Array.isArray(val)
                              ? val.length > 0 ? val.join(", ") : "—"
                              : typeof val === "boolean"
                              ? (val ? "Yes" : "No")
                              : String(val)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Generated Code */}
          {detail?.generated_code && (
            <div className={styles.section}>
              <button
                className={styles.sectionHeader}
                onClick={() => toggleSection("code")}
              >
                <span>Generated Output</span>
                {expandedSections.has("code") ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
              {expandedSections.has("code") && (
                <div className={styles.sectionBody}>
                  <pre className={`${styles.codeBlock} mono`}>{detail.generated_code}</pre>
                </div>
              )}
            </div>
          )}

          {/* Logs */}
          {detail?.logs && detail.logs.length > 0 && (
            <div className={styles.section}>
              <button
                className={styles.sectionHeader}
                onClick={() => toggleSection("logs")}
              >
                <span>Execution Logs ({detail.logs.length})</span>
                {expandedSections.has("logs") ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
              {expandedSections.has("logs") && (
                <div className={styles.sectionBody}>
                  <div className={`${styles.logBox} mono`}>
                    {detail.logs.map((line, i) => (
                      <div
                        key={i}
                        className={`${styles.logLine} ${
                          line.includes("[SUCCESS]") ? styles.logSuccess :
                          line.includes("[WARNING]") ? styles.logWarn :
                          line.includes("[ERROR]") ? styles.logError : ""
                        }`}
                      >
                        {line}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Warnings & Errors */}
          {((detail?.warnings?.length ?? 0) > 0 || (detail?.errors?.length ?? 0) > 0) && (
            <div className={styles.section}>
              <button
                className={styles.sectionHeader}
                onClick={() => toggleSection("issues")}
              >
                <span>
                  Issues ({(detail?.warnings?.length || 0) + (detail?.errors?.length || 0)})
                </span>
                {expandedSections.has("issues") ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
              {expandedSections.has("issues") && (
                <div className={styles.sectionBody}>
                  {detail?.errors?.map((err, i) => (
                    <div key={`e-${i}`} className={styles.issueError}>⛔ {err}</div>
                  ))}
                  {detail?.warnings?.map((warn, i) => (
                    <div key={`w-${i}`} className={styles.issueWarn}>⚠️ {warn}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Finalize: Download CTA */}
          {stageId === "FINALIZE" && isComplete && onDownload && (
            <div className={styles.downloadCta}>
              <button className={styles.downloadBtn} onClick={onDownload}>
                <Download size={18} />
                Download Migration Package
              </button>
              <p className={styles.downloadHint}>
                Includes .lvdash.json, migration report, logs, and validation report
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
