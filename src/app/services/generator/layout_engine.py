"""
layout_engine.py — Lakeview 6-Column Grid Layout Engine (P1.1 Rewrite)
========================================================================
Translates widget relative coordinates and zone geometry into valid Databricks
Lakeview 6-column grid positions using a flow-based row distribution algorithm.

Key improvements over pixel-accurate mapping:
  - Minimum width floors: charts ≥ 2, tables ≥ 3, counters/KPIs ≥ 2
  - Flow-based distribution: widgets fill rows left-to-right, wrapping to next row
  - Normalized Y positions: based on relative ordering, not pixel coordinates
  - Occupancy-based collision avoidance

Grid Constraints (Strictly Enforced):
  - x: 0..5
  - width: 1..6
  - x + width <= 6
  - y: >= 0
  - height: >= 1
"""

from typing import List, Optional
from app.models.universal_model import IntermediateWidget, ChartType


# ── Minimum width floors per chart type ──────────────────────────────────────
# These prevent charts from being squeezed to unreadable 1-column widths.
MIN_WIDTH_BY_TYPE = {
    ChartType.BAR: 2,
    ChartType.LINE: 2,
    ChartType.AREA: 2,
    ChartType.SCATTER: 3,
    ChartType.PIE: 2,
    ChartType.COUNTER: 2,
    ChartType.TABLE: 3,
    ChartType.TEXT_BOX: 2,
    ChartType.HEATMAP: 3,
    ChartType.HISTOGRAM: 2,
    ChartType.BOXPLOT: 3,
    ChartType.COMBO: 3,
    ChartType.MAP: 3,
    ChartType.FILTER_MULTI: 2,
    ChartType.FILTER_SINGLE: 2,
    ChartType.FILTER_DATE: 2,
}

# Default heights per chart type
DEFAULT_HEIGHT_BY_TYPE = {
    ChartType.BAR: 5,
    ChartType.LINE: 5,
    ChartType.AREA: 5,
    ChartType.SCATTER: 5,
    ChartType.PIE: 5,
    ChartType.COUNTER: 3,
    ChartType.TABLE: 6,
    ChartType.TEXT_BOX: 2,
    ChartType.HEATMAP: 5,
    ChartType.HISTOGRAM: 5,
    ChartType.BOXPLOT: 5,
    ChartType.COMBO: 5,
    ChartType.MAP: 5,
    ChartType.FILTER_MULTI: 2,
    ChartType.FILTER_SINGLE: 2,
    ChartType.FILTER_DATE: 2,
}


def clamp_grid_position(grid_x: int, grid_w: int) -> tuple[int, int]:
    """Strictly clamp grid_x and grid_w so x in 0..5, w in 1..6, and x + w <= 6."""
    w = max(1, min(6, grid_w))
    x = max(0, min(5, grid_x))
    if x + w > 6:
        # Prefer shifting x left if possible, or reducing width
        if 6 - w >= 0:
            x = 6 - w
        else:
            w = 6 - x
            if w < 1:
                w = 1
                x = 5
    return x, w


def _get_ideal_width(widget: IntermediateWidget) -> int:
    """Compute the ideal grid width for a widget, respecting minimum floors.
    
    Uses the zone-derived relative width if available, otherwise defaults
    based on chart type. Always enforces minimum width floors.
    """
    chart_type = widget.chart_type
    min_w = MIN_WIDTH_BY_TYPE.get(chart_type, 2)
    pos = widget.position

    if pos.w_rel > 0:
        # Compute from relative width, but enforce floor
        computed = max(1, min(6, round(pos.w_rel * 6)))
        return max(min_w, computed)
    elif pos.grid_w > 0:
        return max(min_w, min(6, pos.grid_w))
    else:
        # Default: full width for tables, half for charts, third for counters/filters
        if chart_type == ChartType.TABLE:
            return 6
        elif chart_type == ChartType.COUNTER:
            return 2
        elif chart_type in (ChartType.FILTER_MULTI, ChartType.FILTER_SINGLE, ChartType.FILTER_DATE):
            return 2
        elif chart_type == ChartType.TEXT_BOX:
            return 6
        else:
            return 3


def _get_ideal_height(widget: IntermediateWidget) -> int:
    """Compute the ideal grid height for a widget."""
    chart_type = widget.chart_type
    default_h = DEFAULT_HEIGHT_BY_TYPE.get(chart_type, 4)
    pos = widget.position

    if pos.h_rel > 0:
        computed = max(2, min(12, round(pos.h_rel * 10)))
        return computed
    elif pos.grid_h > 0:
        return max(2, min(12, pos.grid_h))
    return default_h


def project_to_6column_grid(widgets: List[IntermediateWidget]) -> List[IntermediateWidget]:
    """
    Flow-Based Layout Engine: Distributes widgets across a 6-column grid using
    a row-filling algorithm with occupancy collision avoidance.

    Algorithm:
      1. Sort widgets by their original position (top-to-bottom, left-to-right)
      2. For each widget, compute ideal width and height (with minimum floors)
      3. Place widgets left-to-right in the current row
      4. If no space remains in the current row, wrap to the next row
      5. Use occupancy matrix to prevent overlaps

    Guarantees: x (0..5), width (1..6), x + width <= 6, height >= 1
    """
    if not widgets:
        return widgets

    # Sort widgets by original position: top-to-bottom, then left-to-right
    # Use relative coordinates if available, otherwise grid coordinates
    def sort_key(w: IntermediateWidget):
        pos = w.position
        # Primary: vertical position
        y_key = pos.y_rel if pos.y_rel > 0 else (pos.grid_y / 100.0 if pos.grid_y > 0 else 0)
        # Secondary: horizontal position
        x_key = pos.x_rel if pos.x_rel > 0 else (pos.grid_x / 6.0 if pos.grid_x > 0 else 0)
        return (y_key, x_key)

    sorted_widgets = sorted(widgets, key=sort_key)

    # Occupancy matrix: rows x 6 columns
    occupancy_matrix: List[List[bool]] = []

    def _ensure_capacity(target_rows: int):
        while len(occupancy_matrix) <= target_rows + 20:
            occupancy_matrix.append([False] * 6)

    _ensure_capacity(100)

    def _is_free(x: int, y: int, w: int, h: int) -> bool:
        """Check if a rectangle (x, y, w, h) is free in the occupancy matrix."""
        _ensure_capacity(y + h)
        for r in range(h):
            for c in range(w):
                if occupancy_matrix[y + r][x + c]:
                    return False
        return True

    def _mark_occupied(x: int, y: int, w: int, h: int):
        """Mark a rectangle as occupied."""
        _ensure_capacity(y + h)
        for r in range(h):
            for c in range(w):
                occupancy_matrix[y + r][x + c] = True

    def _find_first_free_row() -> int:
        """Find the first row with any free cell."""
        for y in range(len(occupancy_matrix)):
            if not all(occupancy_matrix[y]):
                return y
        y = len(occupancy_matrix)
        _ensure_capacity(y)
        return y

    for widget in sorted_widgets:
        grid_w = _get_ideal_width(widget)
        grid_h = _get_ideal_height(widget)
        pos = widget.position

        # Determine preferred starting position
        if pos.x_rel > 0:
            preferred_x = max(0, min(5, round(pos.x_rel * 6)))
        elif pos.grid_x > 0:
            preferred_x = max(0, min(5, pos.grid_x))
        else:
            preferred_x = 0

        # Clamp width
        grid_x, grid_w = clamp_grid_position(preferred_x, grid_w)

        # Find placement: scan from row 0 downward, try preferred X first
        placed = False
        start_y = _find_first_free_row()

        for y in range(start_y, start_y + 500):
            _ensure_capacity(y + grid_h)

            # Try preferred x first, then scan all valid x positions
            x_candidates = [grid_x]
            for x in range(0, 7 - grid_w):
                if x != grid_x:
                    x_candidates.append(x)

            for x in x_candidates:
                if x + grid_w > 6:
                    continue

                if _is_free(x, y, grid_w, grid_h):
                    pos.grid_x = x
                    pos.grid_y = y
                    pos.grid_w = grid_w
                    pos.grid_h = grid_h
                    _mark_occupied(x, y, grid_w, grid_h)
                    placed = True
                    break

            if placed:
                break

    return widgets
