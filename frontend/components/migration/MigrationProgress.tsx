import styles from "./MigrationProgress.module.css";

interface MigrationProgressProps {
  progress: number;        // 0–100
  currentStage: string | null;
  elapsedMs: number;
  isRunning: boolean;
}

function formatElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs}s`;
}

export default function MigrationProgress({
  progress,
  currentStage,
  elapsedMs,
  isRunning,
}: MigrationProgressProps) {
  if (!isRunning) return null;

  return (
    <div className={styles.container}>
      <div className={styles.barTrack}>
        <div
          className={`${styles.barFill} ${isRunning ? styles.animate : ""} ${progress >= 100 ? styles.complete : ""}`}
          style={{ width: `${Math.min(progress, 100)}%` }}
        />
      </div>
      {isRunning && (
        <div className={styles.info}>
          <span className={styles.activity}>
            {currentStage ? `Executing: ${currentStage}` : "Starting pipeline..."}
          </span>
          <span className={styles.elapsed}>{formatElapsed(elapsedMs)}</span>
        </div>
      )}
    </div>
  );
}
