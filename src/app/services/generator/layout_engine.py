"""
layout_engine.py — Lakeview 6-Column Grid Layout Engine
========================================================
Translates widget relative coordinates and zone geometry into valid Databricks
Lakeview 6-column grid positions.

Grid Constraints (Strictly Enforced):
  - x: 0..5
  - width: 1..6
  - x + width <= 6
  - y: >= 0
  - height: >= 1
"""

from typing import List
from app.models.universal_model import IntermediateWidget


def clamp_grid_position(grid_x: int, grid_w: int) -> tuple[int, int]:
    """Strictly clamp grid_x and grid_w so x in 0..5, w in 1..6, and x + w <= 6."""
    w = max(1, min(6, grid_w))
    x = max(0, min(5, grid_x))
    if x + w > 6:
        # Prefer reducing width if possible, or shifting x left
        if w > 1:
            w = 6 - x
            if w < 1:
                w = 1
                x = 5
        else:
            x = 5
    return x, w


def project_to_6column_grid(widgets: List[IntermediateWidget]) -> List[IntermediateWidget]:
    """
    Layout Translation Engine: Converts floating/relative containers to Lakeview 6-column grid.
    Guarantees x (0..5), width (1..6), x + width <= 6, height >= 1 for every widget.
    """
    occupancy_matrix: List[List[bool]] = []
    
    def _ensure_capacity(target_rows: int):
        while len(occupancy_matrix) <= target_rows + 20:
            occupancy_matrix.append([False] * 6)

    _ensure_capacity(100)

    for widget in widgets:
        pos = widget.position

        # Determine target grid dimensions
        if pos.w_rel > 0 and pos.h_rel > 0:
            grid_w = max(1, min(6, round(pos.w_rel * 6)))
            grid_h = max(2, min(12, round(pos.h_rel * 8)))
            grid_x = round(pos.x_rel * 6) if pos.x_rel > 0 else pos.grid_x
        else:
            grid_w = pos.grid_w if pos.grid_w > 0 else 6
            grid_h = pos.grid_h if pos.grid_h > 0 else 4
            grid_x = pos.grid_x

        grid_x, grid_w = clamp_grid_position(grid_x, grid_w)

        # Placement search starting at preferred or current y
        start_y = pos.grid_y if pos.grid_y > 0 else 0
        placed = False

        for y in range(start_y, start_y + 1000):
            _ensure_capacity(y + grid_h)

            # Try preferred x first
            target_x_list = [grid_x] + [x for x in range(0, 7 - grid_w) if x != grid_x]

            for x in target_x_list:
                if x + grid_w > 6:
                    continue
                
                collision = any(
                    occupancy_matrix[y + r][x + c]
                    for r in range(grid_h)
                    for c in range(grid_w)
                )

                if not collision:
                    pos.grid_x = x
                    pos.grid_y = y
                    pos.grid_w = grid_w
                    pos.grid_h = grid_h
                    
                    for r in range(grid_h):
                        for c in range(grid_w):
                            occupancy_matrix[y + r][x + c] = True
                    placed = True
                    break
            
            if placed:
                break

    return widgets
