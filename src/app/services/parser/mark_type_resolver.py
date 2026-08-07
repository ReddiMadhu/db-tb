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

    # Direct mappings
    if mark_lower in [
        'pie', 'shape', 'map', 'polygon', 'circle', 'line', 'bar', 'text',
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
        if mark_lower == 'text':
            return 'Text table'
        if mark_lower == 'area':
            return 'Area Chart'
        if mark_lower == 'line':
            return 'Line Chart'
        if mark_lower == 'bar':
            return 'Bar Chart'
        return mark_lower.capitalize()

    # Heuristic Automatic Resolution
    cols_str = " ".join(cols).lower()
    rows_str = " ".join(rows).lower()
    combined_shelves = f"{cols_str} {rows_str}"

    # Generated Lon/Lat on Automatic mark → geographic map
    if "longitude" in combined_shelves or "latitude" in combined_shelves:
        return "Symbol Map"

    has_dates = any(dt in combined_shelves for dt in ['yr:', 'mn:', 'dy:', 'qr:', 'wk:', 'mdy:', 'date:'])
    measure_tokens = ['sum:', 'avg:', 'cnt:', 'count:', 'countd:', 'min:', 'max:', 'attr:', 'median:', 'pct:']
    has_measures = any(agg in combined_shelves for agg in measure_tokens) or (len(measure_bindings or []) > 0)

    if has_dates and has_measures:
        return 'Line Chart'

    if has_measures and len(cols) > 0 and len(rows) > 0:
        cols_has_measure = any(agg in cols_str for agg in measure_tokens)
        rows_has_measure = any(agg in rows_str for agg in measure_tokens)
        if cols_has_measure and rows_has_measure:
            return 'Scatter Plot'
        return 'Bar Chart'

    return 'Text table'
