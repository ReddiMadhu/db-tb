"use client";

import React, { useEffect, useState } from "react";
import {
  acceptLayoutReviewCard,
  getLayoutReviewCardFields,
  overrideLayoutReviewWidget,
  patchLayoutReviewEncodings,
} from "@/lib/api";
import styles from "./VisualConversionDetail.module.css";

type CardLike = {
  id: string;
  status: string;
  lakeview_json?: Record<string, any>;
};

type Props = {
  jobUuid: string;
  card: CardLike;
  onUpdated: (card: any) => void;
  onError: (msg: string) => void;
  onOk: (msg: string) => void;
};

const OVERRIDE_TYPES = ["table", "bar", "pie", "heatmap", "scatter", "line", "counter"];

export default function ReviewCardActions({ jobUuid, card, onUpdated, onError, onOk }: Props) {
  const [busy, setBusy] = useState(false);
  const [fields, setFields] = useState<{ name: string; expression: string }[]>([]);
  const [widgetType, setWidgetType] = useState("bar");
  const [xField, setXField] = useState("");
  const [yField, setYField] = useState("");
  const [colorField, setColorField] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await getLayoutReviewCardFields(jobUuid, card.id);
        if (cancelled) return;
        const fl = res.fields || [];
        setFields(fl);
        setXField(fl[0]?.name || "");
        setYField(fl[1]?.name || "");
        setColorField(fl[2]?.name || "");
        setWidgetType(res.widget_type || card.lakeview_json?.widgetType || "bar");
        setLoaded(true);
      } catch (err: any) {
        if (!cancelled) onError(err?.message || "Failed to load fields");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobUuid, card.id]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (err: any) {
      onError(err?.message || "Action failed");
    } finally {
      setBusy(false);
    }
  };

  if (card.status !== "MANUAL_REVIEW" && card.status !== "UNSUPPORTED") {
    return null;
  }

  return (
    <div
      className={styles.reviewActionsPanel}
      onClick={(e) => e.stopPropagation()}
      style={{
        marginTop: "0.75rem",
        padding: "0.75rem",
        border: "1px solid var(--border-color, #ddd)",
        borderRadius: 8,
        background: "var(--bg-secondary, #f8f9fb)",
        display: "flex",
        flexDirection: "column",
        gap: "0.65rem",
      }}
    >
      <div style={{ fontSize: "0.8rem", fontWeight: 700 }}>Review actions</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        <button
          className={styles.exportBtn}
          disabled={busy}
          onClick={() =>
            run(async () => {
              const res = await acceptLayoutReviewCard(jobUuid, card.id);
              onUpdated(res.card);
              onOk("Card accepted");
            })
          }
        >
          Accept as-is
        </button>
      </div>

      {loaded && (
        <>
          <div style={{ fontSize: "0.75rem", fontWeight: 600 }}>Override widget type</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
            <select
              className={styles.filterSelect}
              value={widgetType}
              onChange={(e) => setWidgetType(e.target.value)}
              disabled={busy}
            >
              {OVERRIDE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select className={styles.filterSelect} value={xField} onChange={(e) => setXField(e.target.value)} disabled={busy}>
              <option value="">x / category</option>
              {fields.map((f) => (
                <option key={`x-${f.name}`} value={f.name}>
                  {f.name}
                </option>
              ))}
            </select>
            <select className={styles.filterSelect} value={yField} onChange={(e) => setYField(e.target.value)} disabled={busy}>
              <option value="">y / measure</option>
              {fields.map((f) => (
                <option key={`y-${f.name}`} value={f.name}>
                  {f.name}
                </option>
              ))}
            </select>
            <select className={styles.filterSelect} value={colorField} onChange={(e) => setColorField(e.target.value)} disabled={busy}>
              <option value="">color (optional)</option>
              {fields.map((f) => (
                <option key={`c-${f.name}`} value={f.name}>
                  {f.name}
                </option>
              ))}
            </select>
            <button
              className={styles.exportBtn}
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const res = await overrideLayoutReviewWidget(jobUuid, card.id, {
                    widget_type: widgetType,
                    x_field: xField || undefined,
                    y_field: yField || undefined,
                    color_field: colorField || undefined,
                  });
                  onUpdated(res.card);
                  onOk(`Overrode to ${widgetType}`);
                })
              }
            >
              Apply override
            </button>
          </div>

          <div style={{ fontSize: "0.75rem", fontWeight: 600 }}>Patch encodings (keep type)</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
            <select className={styles.filterSelect} value={xField} onChange={(e) => setXField(e.target.value)} disabled={busy}>
              <option value="">x</option>
              {fields.map((f) => (
                <option key={`px-${f.name}`} value={f.name}>
                  {f.name}
                </option>
              ))}
            </select>
            <select className={styles.filterSelect} value={yField} onChange={(e) => setYField(e.target.value)} disabled={busy}>
              <option value="">y / angle</option>
              {fields.map((f) => (
                <option key={`py-${f.name}`} value={f.name}>
                  {f.name}
                </option>
              ))}
            </select>
            <select className={styles.filterSelect} value={colorField} onChange={(e) => setColorField(e.target.value)} disabled={busy}>
              <option value="">color</option>
              {fields.map((f) => (
                <option key={`pc-${f.name}`} value={f.name}>
                  {f.name}
                </option>
              ))}
            </select>
            <button
              className={styles.exportBtn}
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const encodings: Record<string, string> = {};
                  if (xField) encodings.x = xField;
                  if (yField) {
                    encodings.y = yField;
                    encodings.angle = yField;
                  }
                  if (colorField) encodings.color = colorField;
                  const res = await patchLayoutReviewEncodings(jobUuid, card.id, encodings);
                  onUpdated(res.card);
                  onOk("Encodings patched");
                })
              }
            >
              Apply encodings
            </button>
          </div>
        </>
      )}
    </div>
  );
}
