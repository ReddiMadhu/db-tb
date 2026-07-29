import { PIPELINE_STAGES, type PipelineStage } from "@/lib/types";
import { Check, AlertCircle } from "lucide-react";
import styles from "./PipelineTracker.module.css";

interface PipelineTrackerProps {
  currentStage: number; // 1 to 10
  status: string; // EXECUTING, COMPLETED, FAILED, PARSED
  onSelectStage?: (stage: PipelineStage) => void;
}

export default function PipelineTracker({
  currentStage,
  status,
  onSelectStage,
}: PipelineTrackerProps) {
  return (
    <div className={styles.trackerContainer}>
      <div className={styles.stagesRow}>
        <div className={styles.lineBackdrop} />

        {PIPELINE_STAGES.map((s) => {
          const isComplete = s.number < currentStage || status === "COMPLETED";
          const isActive = s.number === currentStage && status === "EXECUTING";
          const isFailed = s.number === currentStage && status === "FAILED";

          let stateClass = "";
          if (isComplete) stateClass = styles.complete;
          else if (isActive) stateClass = styles.active;
          else if (isFailed) stateClass = styles.failed;

          return (
            <div
              key={s.key}
              className={`${styles.stageItem} ${stateClass}`}
              onClick={() => onSelectStage?.(s.key)}
            >
              <div className={styles.node}>
                {isComplete ? (
                  <Check size={14} />
                ) : isFailed ? (
                  <AlertCircle size={14} />
                ) : (
                  s.number
                )}
              </div>
              <span className={styles.label}>{s.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
