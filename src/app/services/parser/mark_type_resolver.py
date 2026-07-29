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
    if mark_lower in ['pie', 'shape', 'map', 'polygon', 'circle', 'line', 'bar', 'text', 'ganttbar']:
        if mark_lower == 'ganttbar':
            return 'Gantt Bar'
        if mark_lower == 'circle':
            return 'Scatter Plot'
        return mark_lower.capitalize()

    # Heuristic Automatic Resolution
    cols_str = " ".join(cols).lower()
    rows_str = " ".join(rows).lower()
    combined_shelves = f"{cols_str} {rows_str}"
    
    has_dates = any(dt in combined_shelves for dt in ['yr:', 'mn:', 'dy:', 'qr:', 'wk:', 'mdy:', 'date:'])
    measure_tokens = ['sum:', 'avg:', 'cnt:', 'count:', 'countd:', 'min:', 'max:', 'attr:', 'median:', 'pct:']
    has_measures = any(agg in combined_shelves for agg in measure_tokens) or (len(measure_bindings or []) > 0)
    
    if has_dates and has_measures:
        return 'Line'
    
    if has_measures and len(cols) > 0 and len(rows) > 0:
        cols_has_measure = any(agg in cols_str for agg in measure_tokens)
        rows_has_measure = any(agg in rows_str for agg in measure_tokens)
        if cols_has_measure and rows_has_measure:
            return 'Scatter Plot'
        return 'Bar'
        
    if has_measures:
        return 'Text Table / KPI'
        
    if len(cols) > 0 and len(rows) > 0:
        return 'Text Table'

    return 'Text / Value'
