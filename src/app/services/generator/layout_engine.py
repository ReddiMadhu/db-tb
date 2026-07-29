from typing import List
from app.models.universal_model import IntermediateWidget, IntermediatePosition


def project_to_6column_grid(widgets: List[IntermediateWidget]) -> List[IntermediateWidget]:
    """
    Layout Translation Engine: Converts floating/relative containers to Lakeview 6-column grid.
    Grid constraints: x (0..5), width (1..6), x + width <= 6, height >= 1.
    Dynamically expands occupancy matrix height to accommodate any number of widgets.
    """
    occupancy_matrix = [[False] * 6 for _ in range(500)]  # 500 rows grid capacity

    current_y = 0
    for widget in widgets:
        pos = widget.position
        grid_w = max(1, min(6, round(pos.w_rel * 6))) if pos.w_rel > 0 else 6
        grid_h = max(2, min(12, round(pos.h_rel * 8))) if pos.h_rel > 0 else 4

        placed = False
        for y in range(current_y, 480):
            # Ensure occupancy matrix has enough rows
            while len(occupancy_matrix) <= y + grid_h + 10:
                occupancy_matrix.append([False] * 6)

            for x in range(0, 7 - grid_w):
                collision = any(occupancy_matrix[y + r][x + c] for r in range(grid_h) for c in range(grid_w))
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
