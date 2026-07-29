import React from "react";
import styles from "./Card.module.css";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  clickable?: boolean;
}

export default function Card({ children, clickable, className = "", ...props }: CardProps) {
  return (
    <div
      className={`${styles.card} ${clickable ? styles.clickable : ""} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
