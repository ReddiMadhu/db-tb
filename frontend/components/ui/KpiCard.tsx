import styles from "./KpiCard.module.css";

interface KpiCardProps {
  value: string | number;
  label: string;
  icon?: React.ReactNode;
  accentColor?: string;
  loading?: boolean;
}

export default function KpiCard({ value, label, icon, accentColor, loading }: KpiCardProps) {
  return (
    <div className={styles.card}>
      {icon && (
        <div className={styles.iconWrap} style={accentColor ? { color: accentColor } : undefined}>
          {icon}
        </div>
      )}
      <div className={styles.content}>
        <div
          className={styles.value}
          style={accentColor ? { color: accentColor } : undefined}
        >
          {loading ? <span className={styles.skeleton} /> : value}
        </div>
        <div className={styles.label}>{label}</div>
      </div>
    </div>
  );
}
