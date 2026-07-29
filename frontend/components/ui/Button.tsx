"use client";

import React from "react";
import { Loader2 } from "lucide-react";
import styles from "./Button.module.css";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  icon?: React.ReactNode;
  isLoading?: boolean;
  loadingText?: string;
}

export default function Button({
  children,
  variant = "secondary",
  size = "md",
  icon,
  isLoading = false,
  loadingText,
  disabled,
  className = "",
  ...props
}: ButtonProps) {
  const sizeClass = size === "sm" ? styles.sm : size === "lg" ? styles.lg : "";
  const isDisabled = disabled || isLoading;

  return (
    <button
      className={`${styles.button} ${styles[variant]} ${sizeClass} ${className}`}
      disabled={isDisabled}
      {...props}
    >
      {isLoading ? (
        <>
          <Loader2 size={size === "sm" ? 14 : size === "lg" ? 18 : 16} className="spin" />
          <span>{loadingText || children}</span>
        </>
      ) : (
        <>
          {icon && <span className={styles.icon}>{icon}</span>}
          <span>{children}</span>
        </>
      )}
    </button>
  );
}
