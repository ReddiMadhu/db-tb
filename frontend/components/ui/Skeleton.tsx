import styles from "./Skeleton.module.css";

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  className?: string;
  style?: React.CSSProperties;
}

export default function Skeleton({
  width,
  height,
  borderRadius,
  className = "",
  style = {},
}: SkeletonProps) {
  return (
    <div
      className={`${styles.skeleton} ${className}`}
      style={{
        width: typeof width === "number" ? `${width}px` : width,
        height: typeof height === "number" ? `${height}px` : height,
        borderRadius: typeof borderRadius === "number" ? `${borderRadius}px` : borderRadius,
        ...style,
      }}
    />
  );
}

export function SkeletonCard() {
  return (
    <div className={styles.cardSkeleton}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Skeleton width="60%" height="20px" />
        <Skeleton width="70px" height="22px" borderRadius="12px" />
      </div>
      <Skeleton width="85%" height="14px" />
      <Skeleton width="45%" height="14px" />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "0.5rem" }}>
        <Skeleton width="30%" height="12px" />
        <Skeleton width="80px" height="28px" borderRadius="6px" />
      </div>
    </div>
  );
}

export function SkeletonTable({ rows = 4 }: { rows?: number }) {
  return (
    <div className={styles.tableSkeleton}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
        <Skeleton width="25%" height="18px" />
        <Skeleton width="15%" height="18px" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={styles.tableRow}>
          <Skeleton width="40%" height="14px" />
          <Skeleton width="20%" height="14px" />
          <Skeleton width="15%" height="14px" />
          <Skeleton width="60px" height="24px" borderRadius="4px" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonList({ items = 3 }: { items?: number }) {
  return (
    <div className={styles.listSkeleton}>
      {Array.from({ length: items }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
