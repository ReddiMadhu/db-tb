from typing import List, Optional


def resolve_mark_type(
    raw_mark_type: Optional[str],
    cols: List[str],
    rows: List[str],
    measure_bindings: List[dict] = None
) -> str:
    """
    Resolves Tableau mark types to canonical visual mark types.
    Handles 'Automatic' inference based on shelf dimensions/dates/measures.
    """
    mark_lower = (raw_mark_type or 'automatic').lower()
    cols = cols or []
    rows = rows or []
    measure_bindings = measure_bindings or []

    cols_str = " ".join(cols).lower()
    rows_str = " ".join(rows).lower()
    combined_shelves = f"{cols_str} {rows_str}"

    measure_tokens = [
        'sum:', 'avg:', 'cnt:', 'count:', 'countd:', 'min:', 'max:',
        'attr:', 'median:', 'pct:',
    ]
    has_dates = any(
        dt in combined_shelves
        for dt in ['yr:', 'mn:', 'dy:', 'qr:', 'wk:', 'mdy:', 'date:']
    )
    has_measures = any(agg in combined_shelves for agg in measure_tokens) or (
        len(measure_bindings) > 0
    )
    cols_has_measure = any(agg in cols_str for agg in measure_tokens)
    rows_has_measure = any(agg in rows_str for agg in measure_tokens)
    cols_has_dim = bool(cols) and not cols_has_measure
    rows_has_dim = bool(rows) and not rows_has_measure

    # Direct mappings (text deferred — may be KPI)
    if mark_lower in [
        'pie', 'shape', 'map', 'polygon', 'circle', 'line', 'bar',
        'ganttbar', 'square', 'heatmap', 'area',
    ]:
        if mark_lower == 'ganttbar':
            return 'Gantt Bar'
        if mark_lower == 'circle':
            return 'Scatter Plot'
        if mark_lower in ('square', 'heatmap'):
            return 'Heatmap (square)'
        if mark_lower == 'pie':
            return 'Pie chart'
        if mark_lower == 'area':
            return 'Area Chart'
        if mark_lower == 'line':
            return 'Line Chart'
        if mark_lower == 'bar':
            return 'Bar Chart'
        if mark_lower == 'map' or mark_lower == 'polygon':
            return mark_lower.capitalize() if mark_lower != 'map' else 'Map'
        if mark_lower == 'shape':
            return 'Shape'
        return mark_lower.capitalize()

    # Generated Lon/Lat → geographic map
    if "longitude" in combined_shelves or "latitude" in combined_shelves:
        return "Symbol Map"

    # Text mark: single-measure big number → KPI; otherwise text table
    if mark_lower == 'text':
        if has_measures and not cols_has_dim and not rows_has_dim:
            return 'Text Table / KPI'
        return 'Text table'

    # Automatic / unknown heuristics
    if has_dates and has_measures:
        return 'Line Chart'

    if has_measures and len(cols) > 0 and len(rows) > 0:
        if cols_has_measure and rows_has_measure:
            return 'Scatter Plot'
        return 'Bar Chart'

    # Single-measure automatic with no categorical shelves → KPI counter
    if has_measures and not cols_has_dim and not rows_has_dim:
        return 'Text Table / KPI'

    return 'Text table'
