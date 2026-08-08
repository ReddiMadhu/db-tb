"use client";

import React, { useMemo, useState, useCallback, useRef } from "react";
import { Database } from "lucide-react";
import type { JoinRelation } from "./RelationshipDiagram";
import styles from "./DataModelCanvas.module.css";

interface DataModelCanvasProps {
  tables: string[];
  joins: JoinRelation[];
  activeTable?: string | null;
  onSelectTable: (table: string) => void;
  fallbackLabel?: string;
}

interface GraphEdge {
  id: string;
  left_table: string;
  right_table: string;
  left_column: string;
  right_column: string;
  join_type?: string;
  label: string;
}

interface NodePos {
  x: number;
  y: number;
  w: number;
  h: number;
}

const NODE_W = 160;
const NODE_H = 40;
const PAD = 28;
const MIN_W = 420;
const MIN_H = 220;

function buildEdges(joins: JoinRelation[]): GraphEdge[] {
  const seen = new Set<string>();
  const edges: GraphEdge[] = [];

  joins.forEach((j, idx) => {
    const left = (j.left_table || "").trim();
    const right = (j.right_table || "").trim();
    if (!left || !right) return;

    const pair = [left.toLowerCase(), right.toLowerCase()].sort();
    const colKey = `${(j.left_column || "").toLowerCase()}|${(j.right_column || "").toLowerCase()}`;
    const dedupeKey = `${pair[0]}::${pair[1]}::${colKey}`;
    if (seen.has(dedupeKey)) return;
    seen.add(dedupeKey);

    const lCol = j.left_column || "?";
    const rCol = j.right_column || "?";
    const typePart = j.join_type ? ` (${j.join_type})` : "";
    const label = `${left}.${lCol} = ${right}.${rCol}${typePart}`;

    edges.push({
      id: `e-${idx}-${dedupeKey}`,
      left_table: left,
      right_table: right,
      left_column: lCol,
      right_column: rCol,
      join_type: j.join_type,
      label,
    });
  });

  return edges;
}

function layoutNodes(tables: string[]): { positions: Map<string, NodePos>; width: number; height: number } {
  const positions = new Map<string, NodePos>();
  const n = tables.length;

  if (n === 0) {
    return { positions, width: MIN_W, height: MIN_H };
  }

  if (n === 1) {
    positions.set(tables[0], {
      x: MIN_W / 2 - NODE_W / 2,
      y: MIN_H / 2 - NODE_H / 2,
      w: NODE_W,
      h: NODE_H,
    });
    return { positions, width: MIN_W, height: MIN_H };
  }

  const radius = Math.max(90, 40 + n * 28);
  const cx = radius + PAD + NODE_W / 2;
  const cy = radius + PAD + NODE_H / 2;
  const width = Math.max(MIN_W, 2 * (radius + PAD) + NODE_W);
  const height = Math.max(MIN_H, 2 * (radius + PAD) + NODE_H);

  tables.forEach((name, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    const x = cx + radius * Math.cos(angle) - NODE_W / 2;
    const y = cy + radius * Math.sin(angle) - NODE_H / 2;
    positions.set(name, { x, y, w: NODE_W, h: NODE_H });
  });

  return { positions, width, height };
}

function centerOf(pos: NodePos): { x: number; y: number } {
  return { x: pos.x + pos.w / 2, y: pos.y + pos.h / 2 };
}

function findTableKey(map: Map<string, NodePos>, name: string): string | null {
  const lower = name.toLowerCase();
  for (const key of map.keys()) {
    if (key.toLowerCase() === lower) return key;
  }
  return null;
}

export default function DataModelCanvas({
  tables,
  joins,
  activeTable,
  onSelectTable,
  fallbackLabel = "Logical Model",
}: DataModelCanvasProps) {
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);

  const displayTables = useMemo(() => {
    if (tables.length > 0) return tables;
    return [fallbackLabel];
  }, [tables, fallbackLabel]);

  const edges = useMemo(() => buildEdges(joins), [joins]);

  const { positions, width, height } = useMemo(
    () => layoutNodes(displayTables),
    [displayTables]
  );

  const activeLower = activeTable?.toLowerCase() ?? "";

  const updateTooltip = useCallback((e: React.MouseEvent, edge: GraphEdge) => {
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect) return;
    setHoveredEdge(edge.id);
    setTooltip({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top - 10,
      text: edge.label,
    });
  }, []);

  const clearTooltip = useCallback(() => {
    setHoveredEdge(null);
    setTooltip(null);
  }, []);

  return (
    <div className={styles.canvas} style={{ minHeight: height }}>
      <div
        ref={stageRef}
        className={styles.stage}
        style={{ width, height }}
      >
        <svg
          className={styles.edgeLayer}
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
        >
          {edges.map((edge) => {
            const leftKey = findTableKey(positions, edge.left_table);
            const rightKey = findTableKey(positions, edge.right_table);
            if (!leftKey || !rightKey) return null;

            const a = centerOf(positions.get(leftKey)!);
            const b = centerOf(positions.get(rightKey)!);
            const isActive =
              Boolean(activeLower) &&
              (edge.left_table.toLowerCase() === activeLower ||
                edge.right_table.toLowerCase() === activeLower);
            const isHovered = hoveredEdge === edge.id;

            return (
              <g key={edge.id}>
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  className={styles.edgeHit}
                  onMouseEnter={(ev) => updateTooltip(ev, edge)}
                  onMouseMove={(ev) => updateTooltip(ev, edge)}
                  onMouseLeave={clearTooltip}
                />
                <line
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  className={`${styles.edgeLine} ${isActive ? styles.edgeLineActive : ""} ${
                    isHovered ? styles.edgeLineHovered : ""
                  }`}
                  pointerEvents="none"
                />
                <title>{edge.label}</title>
              </g>
            );
          })}
        </svg>

        {displayTables.map((name) => {
          const pos = positions.get(name);
          if (!pos) return null;
          const selected = Boolean(activeLower) && name.toLowerCase() === activeLower;
          return (
            <button
              key={name}
              type="button"
              className={`${styles.tableNode} ${selected ? styles.nodeSelected : ""}`}
              style={{
                left: pos.x,
                top: pos.y,
                width: pos.w,
                height: pos.h,
              }}
              onClick={() => onSelectTable(name)}
              title={name}
            >
              <Database size={14} />
              <span className={styles.tableNodeLabel}>{name}</span>
            </button>
          );
        })}

        {tooltip && (
          <div
            className={styles.edgeTooltip}
            style={{ left: tooltip.x, top: tooltip.y }}
            role="tooltip"
          >
            {tooltip.text}
          </div>
        )}
      </div>
    </div>
  );
}
