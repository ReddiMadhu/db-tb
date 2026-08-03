"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertCircle, RefreshCw, Home, ChevronDown, ChevronUp } from "lucide-react";
import Button from "@/components/ui/Button";
import styles from "./ErrorBoundary.module.css";

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  showDetails: boolean;
  requestId: string;
}

export default class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
    showDetails: false,
    requestId: `req-${Math.random().toString(36).slice(2, 8).toUpperCase()}`,
  };

  public static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught React runtime error:", error, errorInfo);
    this.setState({ errorInfo });
  }

  private handleReload = () => {
    window.location.reload();
  };

  private handleGoHome = () => {
    window.location.href = "/";
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className={styles.container}>
          <div className={styles.card}>
            <div className={styles.iconCircle}>
              <AlertCircle size={32} />
            </div>

            <h1 className={styles.title}>System Recoverable Error</h1>
            <p className={styles.description}>
              The application encountered an unhandled rendering error. You can reload the application or return to the main dashboard.
            </p>

            <div className={`${styles.requestIdBadge} mono`}>
              Request ID: {this.state.requestId}
            </div>

            <div className={styles.actions}>
              <Button variant="primary" icon={<RefreshCw size={16} />} onClick={this.handleReload}>
                Reload Application
              </Button>
              <Button variant="secondary" icon={<Home size={16} />} onClick={this.handleGoHome}>
                Return to Dashboard
              </Button>
            </div>

            <div style={{ marginTop: "1.5rem" }}>
              <button
                onClick={() => this.setState({ showDetails: !this.state.showDetails })}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--text-secondary)",
                  fontSize: "0.8125rem",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.35rem",
                }}
              >
                <span>{this.state.showDetails ? "Hide Stack Trace" : "Show Technical Details"}</span>
                {this.state.showDetails ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>

              {this.state.showDetails && (
                <pre className={`${styles.details} mono`}>
                  {this.state.error?.toString()}
                  {"\n"}
                  {this.state.errorInfo?.componentStack}
                </pre>
              )}
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
