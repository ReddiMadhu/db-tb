"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { Play, Rocket, ArrowLeft, RefreshCw } from "lucide-react";
import PipelineStepper from "@/components/migration/PipelineStepper";
import StageDetailPanel from "@/components/migration/StageDetailPanel";
import MigrationProgress from "@/components/migration/MigrationProgress";
import StatusBadge from "@/components/ui/StatusBadge";
import {
  getMigrationStatus,
  executePipeline,
  getStages,
  getProgress,
  getLakeviewJson,
} from "@/lib/api";
import type { StageSummary, PipelineProgress as PipelineProgressType } from "@/lib/types";
import styles from "./Workspace.module.css";

export default function MigrationWorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const jobUuid = params.jobUuid as string;

  const [status, setStatus] = useState<string>("INITIALIZED");
  const [filename, setFilename] = useState<string>("");
  const [stages, setStages] = useState<StageSummary[]>([]);
  const [selectedStageId, setSelectedStageId] = useState<string>("UPLOAD");
  const [progress, setProgress] = useState<PipelineProgressType | null>(null);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch initial status + stages
  const fetchInitial = useCallback(async () => {
    try {
      const [statusRes, stagesRes] = await Promise.all([
        getMigrationStatus(jobUuid),
        getStages(jobUuid),
      ]);
      setStatus(statusRes.status);
      setFilename(statusRes.filename || "");
      setStages(stagesRes.stages);

      // Auto-select a relevant stage
      const runningStage = stagesRes.stages.find((s) => s.status === "RUNNING");
      const failedStage = stagesRes.stages.find((s) => s.status === "FAILED");
      if (runningStage) setSelectedStageId(runningStage.stage_id);
      else if (failedStage) setSelectedStageId(failedStage.stage_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load migration");
    } finally {
      setLoading(false);
    }
  }, [jobUuid]);

  useEffect(() => {
    fetchInitial();
  }, [fetchInitial]);

  // Polling during execution
  useEffect(() => {
    if (status !== "EXECUTING") {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }

    const poll = async () => {
      try {
        const [stagesRes, progressRes] = await Promise.all([
          getStages(jobUuid),
          getProgress(jobUuid),
        ]);
        setStages(stagesRes.stages);
        setProgress(progressRes);

        // Auto-follow the running stage
        const running = stagesRes.stages.find((s) => s.status === "RUNNING");
        if (running) setSelectedStageId(running.stage_id);

        // Stop polling when done
        if (progressRes.is_complete || progressRes.is_failed) {
          setStatus(progressRes.job_status);
          setExecuting(false);
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch {
        // Silently retry on transient errors
      }
    };

    pollRef.current = setInterval(poll, 2500);
    poll(); // immediate first poll

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [status, jobUuid]);

  // Execute pipeline
  const handleExecute = async () => {
    setExecuting(true);
    setError(null);
    setStatus("EXECUTING");
    try {
      await executePipeline(jobUuid);
      // After execution completes, refresh
      const [statusRes, stagesRes] = await Promise.all([
        getMigrationStatus(jobUuid),
        getStages(jobUuid),
      ]);
      setStatus(statusRes.status);
      setStages(stagesRes.stages);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Pipeline execution failed");
      const statusRes = await getMigrationStatus(jobUuid).catch(() => null);
      if (statusRes) setStatus(statusRes.status);
    } finally {
      setExecuting(false);
    }
  };

  // Download handler for Finalize stage
  const handleDownload = async () => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1"}/migrations/${jobUuid}/json`
      );
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${jobUuid}.lvdash.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Download failed");
    }
  };

  const isComplete = ["COMPLETED", "DEPLOYED", "FAILED_VALIDATION"].includes(status);
  const canExecute = ["PARSED", "NEEDS_MAPPING", "FAILED"].includes(status);

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingSkeleton}>
          <div className={styles.skeletonBar} />
          <div className={styles.skeletonStepper} />
          <div className={styles.skeletonPanel} />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {/* Progress Bar */}
      <MigrationProgress
        progress={progress?.overall_progress || (isComplete ? 100 : 0)}
        currentStage={progress?.current_activity || null}
        elapsedMs={progress?.elapsed_ms || 0}
        isRunning={status === "EXECUTING"}
      />

      {/* Action Bar */}
      <div className={styles.actionBar}>
        <div className={styles.actionBarLeft}>
          <button
            className={styles.backBtn}
            onClick={() => router.push("/migrations")}
            title="Back to migrations"
          >
            <ArrowLeft size={16} />
          </button>
          <div className={styles.jobInfo}>
            <h1 className={styles.jobFilename}>{filename || jobUuid}</h1>
            <StatusBadge status={status} size="md" />
          </div>
        </div>
        <div className={styles.actionBarRight}>
          {canExecute && (
            <button
              className={styles.runBtn}
              onClick={handleExecute}
              disabled={executing}
            >
              {executing ? (
                <RefreshCw size={16} className="spin" />
              ) : (
                <Play size={16} />
              )}
              {executing ? "Executing..." : "Run Pipeline"}
            </button>
          )}
          {isComplete && (
            <button className={styles.deployBtn} onClick={handleDownload}>
              <Rocket size={16} />
              Download .lvdash.json
            </button>
          )}
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className={styles.errorBanner}>
          <span>{error}</span>
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* Pipeline Stepper */}
      <div className={styles.stepperSection}>
        <PipelineStepper
          stages={stages}
          selectedStageId={selectedStageId}
          onSelectStage={setSelectedStageId}
        />
      </div>

      {/* Stage Detail Panel */}
      <div className={styles.detailSection}>
        <StageDetailPanel
          key={selectedStageId}
          jobUuid={jobUuid}
          stageId={selectedStageId}
          isComplete={isComplete}
          onDownload={handleDownload}
        />
      </div>
    </div>
  );
}
