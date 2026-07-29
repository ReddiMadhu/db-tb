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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <Skeleton width="60%" height="20px" />
        <Skeleton width="70px" height="22px" borderRadius="12px" />
      </div>
      <Skeleton width="80%" height="14px" style={{ marginBottom: "0.5rem" }} />
      <Skeleton width="40%" height="14px" style={{ marginBottom: "1rem" }} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Skeleton width="30%" height="12px" />
        <Skeleton width="80px" height="28px" borderRadius="6px" />
      </div>
    </div>
  );
}
