"use client";

import {
  Upload, FileSearch, Calculator, GitBranch, Code,
  LayoutDashboard, ShieldCheck, Rocket, PackageCheck,
  Check, AlertTriangle, XCircle, SkipForward, Loader2,
} from "lucide-react";
import { PIPELINE_STAGES } from "@/lib/pipeline.config";
import type { StageStatus, StageSummary } from "@/lib/types";
import styles from "./PipelineStepper.module.css";

const ICON_MAP: Record<string, React.ReactNode> = {
  Upload: <Upload size={16} />,
  FileSearch: <FileSearch size={16} />,
  Calculator: <Calculator size={16} />,
  GitBranch: <GitBranch size={16} />,
  Code: <Code size={16} />,
  LayoutDashboard: <LayoutDashboard size={16} />,
  ShieldCheck: <ShieldCheck size={16} />,
  Rocket: <Rocket size={16} />,
  PackageCheck: <PackageCheck size={16} />,
};

function getStatusIcon(status: StageStatus) {
  switch (status) {
    case "COMPLETED": return null;
    case "RUNNING": return <Loader2 size={14} className="spin" />;
    case "WARNING": return <AlertTriangle size={14} />;
    case "FAILED": return <XCircle size={14} />;
    case "SKIPPED": return <SkipForward size={14} />;
    default: return null;
  }
}

interface PipelineStepperProps {
  stages: StageSummary[];
  selectedStageId: string;
  onSelectStage: (stageId: string) => void;
}

export default function PipelineStepper({
  stages,
  selectedStageId,
  onSelectStage,
}: PipelineStepperProps) {
  // Build a lookup from stage data
  const stageStatusMap: Record<string, StageStatus> = {};
  for (const s of stages) {
    stageStatusMap[s.stage_id] = s.status;
  }

  return (
    <div className={styles.stepper}>
      {PIPELINE_STAGES.map((config, idx) => {
        const status: StageStatus = stageStatusMap[config.id] || "WAITING";
        const isSelected = config.id === selectedStageId;
        const isLast = idx === PIPELINE_STAGES.length - 1;

        const statusClass = styles[status.toLowerCase()] || "";
        const statusIcon = getStatusIcon(status);
        const stageIcon = ICON_MAP[config.icon];

        return (
          <div key={config.id} className={styles.stageGroup}>
            {/* Node */}
            <button
              className={`${styles.node} ${statusClass} ${isSelected ? styles.selected : ""}`}
              onClick={() => onSelectStage(config.id)}
              title={config.title}
              aria-label={`${config.title} — ${status}`}
              aria-current={isSelected ? "step" : undefined}
            >
              <div className={styles.nodeIcon}>
                {statusIcon || stageIcon}
              </div>
              {status === "RUNNING" && (
                <span className={styles.ripple} />
              )}
            </button>

            {/* Label */}
            <span className={`${styles.label} ${isSelected ? styles.labelSelected : ""}`}>
              {config.title}
            </span>

            {/* Connector line */}
            {!isLast && (
              <div className={`${styles.connector} ${
                status === "COMPLETED" || status === "WARNING" ? styles.connectorDone : ""
              } ${status === "RUNNING" ? styles.connectorActive : ""}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
