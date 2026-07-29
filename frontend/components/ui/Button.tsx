import React from "react";
import styles from "./Button.module.css";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  icon?: React.ReactNode;
}

export default function Button({
  children,
  variant = "secondary",
  size = "md",
  icon,
  className = "",
  ...props
}: ButtonProps) {
  const sizeClass = size === "sm" ? styles.sm : size === "lg" ? styles.lg : "";
  return (
    <button
      className={`${styles.button} ${styles[variant]} ${sizeClass} ${className}`}
      {...props}
    >
      {icon && <span className={styles.icon}>{icon}</span>}
      {children}
    </button>
  );
}
