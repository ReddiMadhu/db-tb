import json
import os
import re
from typing import Dict, List, Any
from app.models.lakeview_model import LakeviewDashboard
from app.services.generator.widget_factory import validate_widget_spec

try:
    import jsonschema
except ImportError:
    jsonschema = None

try:
    import sqlglot
except ImportError:
    sqlglot = None

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "24_json_schema.json")

def _make_safe_alias_local(field_name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]', '_', field_name).strip('_') or field_name

# Patterns for semantic validation
UNRESOLVED_TABLE_RE = re.compile(
    r'(?:FROM|JOIN)\s+[`"]?(Sheet\d*\$\d*|sample_table|Extract)[`"]?(?:\s|$|,)',
    re.IGNORECASE
)
PSEUDO_FIELD_PATTERNS = [
    re.compile(r':?Measure\s+(Names|Values)', re.IGNORECASE),
    re.compile(r'(Longitude|Latitude)\s*\(generated\)', re.IGNORECASE),
    re.compile(r'\w+\s*\(bin\)', re.IGNORECASE),
    re.compile(r'\bctd:', re.IGNORECASE),
]
TABLEAU_INTERNAL_RE = re.compile(
    r'\[?(excel-direct|textscan)\.[^\]]*\]?', re.IGNORECASE
)
SUPPORTED_WIDGET_TYPES = {
    'bar', 'line', 'area', 'scatter', 'pie', 'counter', 'table',
    'filter-multi-select', 'filter-single-select', 'filter-date-range-picker',
    'pivot', 'heatmap',
}

AGG_FUNC_RE = re.compile(
    r'\b(SUM|AVG|COUNT|MIN|MAX|PERCENTILE|PERCENTILE_APPROX|MEDIAN|STDDEV|VARIANCE|'
    r'ANY_VALUE|FIRST|LAST|COLLECT_LIST|COLLECT_SET|APPROX_COUNT_DISTINCT)\s*\(',
    re.IGNORECASE,
)
_SET_OP_RE = re.compile(r'\b(?:UNION\s+ALL|UNION|INTERSECT|EXCEPT|MINUS)\b', re.IGNORECASE)
_SELECT_RE = re.compile(r'\bSELECT\b', re.IGNORECASE)
_FROM_RE = re.compile(r'\bFROM\b', re.IGNORECASE)
_GROUP_BY_RE = re.compile(r'\bGROUP\s+BY\b', re.IGNORECASE)
_POST_GROUP_RE = re.compile(r'\b(?:HAVING|ORDER\s+BY|LIMIT|WINDOW|QUALIFY)\b', re.IGNORECASE)
_AS_RE = re.compile(r'\s+AS\s+', re.IGNORECASE)
_COMMA_RE = re.compile(r',')
_QUOTED_IDENT_RE = re.compile(r'`([^`]+)`')
_DOTTED_IDENT_RE = re.compile(
    r'\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*(\()?'
)
_SQL_NON_COLUMN_WORDS = {
    "AS", "DISTINCT", "ALL", "CASE", "WHEN", "THEN", "ELSE", "END", "AND", "OR", "NOT",
    "NULL", "TRUE", "FALSE", "IS", "IN", "LIKE", "BETWEEN", "INTERVAL", "OVER",
    "PARTITION", "BY", "ASC", "DESC", "NULLS", "FIRST", "LAST",
    "INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "DOUBLE", "FLOAT", "REAL",
    "DECIMAL", "NUMERIC", "STRING", "VARCHAR", "CHAR", "BOOLEAN", "DATE", "TIMESTAMP",
}


def _top_level_spans(sql: str, pattern: "re.Pattern") -> List[tuple]:
    """Spans of ``pattern`` matches outside string/identifier quotes and parentheses."""
    spans: List[tuple] = []
    depth = 0
    quote = ""
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if quote:
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth -= 1
            i += 1
            continue
        if depth == 0:
            m = pattern.match(sql, i)
            if m and m.end() > m.start():
                spans.append((m.start(), m.end()))
                i = m.end()
                continue
        i += 1
    return spans


def _split_top_level(text: str, pattern: "re.Pattern") -> List[str]:
    parts: List[str] = []
    start = 0
    for s, e in _top_level_spans(text, pattern):
        parts.append(text[start:s])
        start = e
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _referenced_columns(expr: str) -> List[str]:
    """Column identifiers an expression reads. Backticked names win when present."""
    quoted = _QUOTED_IDENT_RE.findall(expr)
    if quoted:
        return quoted
    stripped = re.sub(r"'[^']*'", " ", expr)
    stripped = re.sub(r'"[^"]*"', " ", stripped)
    cols: List[str] = []
    for m in _DOTTED_IDENT_RE.finditer(stripped):
        if m.group(2):  # function call, not a column
            continue
        name = m.group(1).split(".")[-1]
        if name.upper() in _SQL_NON_COLUMN_WORDS:
            continue
        cols.append(name)
    return cols


def _branch_unaggregated_columns(branch: str) -> List[str]:
    """Columns projected without aggregation and absent from GROUP BY, for one branch."""
    if not AGG_FUNC_RE.search(branch):
        return []
    group_spans = _top_level_spans(branch, _GROUP_BY_RE)
    select_spans = _top_level_spans(branch, _SELECT_RE)
    from_spans = _top_level_spans(branch, _FROM_RE)
    if not group_spans or not select_spans or not from_spans:
        return []
    sel_end = select_spans[0][1]
    from_start = next((s for s, _ in from_spans if s > sel_end), None)
    if from_start is None:
        return []

    group_clause = branch[group_spans[0][1]:]
    post = _top_level_spans(group_clause, _POST_GROUP_RE)
    if post:
        group_clause = group_clause[:post[0][0]]
    group_items = _split_top_level(group_clause, _COMMA_RE)
    group_ordinals = {g for g in group_items if g.isdigit()}
    group_cols = {
        c.upper() for g in group_items for c in _referenced_columns(g)
    }

    missing: List[str] = []
    for idx, item in enumerate(_split_top_level(branch[sel_end:from_start], _COMMA_RE), 1):
        if item == "*" or item.upper() == "DISTINCT":
            continue
        if AGG_FUNC_RE.search(item) or str(idx) in group_ordinals:
            continue
        expr = _split_top_level(item, _AS_RE)[0]
        for col in _referenced_columns(expr):
            if col.upper() not in group_cols:
                missing.append(col)
    return missing


def _unaggregated_columns(query: str) -> List[str]:
    """MISSING_AGGREGATION offenders, evaluating each UNION/EXCEPT branch separately."""
    seen: set = set()
    offenders: List[str] = []
    for branch in _split_top_level(query, _SET_OP_RE):
        for col in _branch_unaggregated_columns(branch):
            if col.upper() not in seen:
                seen.add(col.upper())
                offenders.append(col)
    return offenders


def _select_item_output_name(item: str) -> str:
    """Resolve the output column name of one SELECT list item."""
    item = (item or "").strip()
    if not item or item == "*":
        return ""
    # SELECT DISTINCT col — DISTINCT is a modifier, not the item itself
    if item.upper().startswith("DISTINCT"):
        rest = item[8:].lstrip()
        if not rest:
            return ""
        item = rest
    # Explicit AS alias — prefer the last AS segment (handles CAST(... AS DOUBLE) AS `Value`)
    parts = _split_top_level(item, _AS_RE)
    if len(parts) >= 2:
        alias = parts[-1].strip()
        quoted = _QUOTED_IDENT_RE.findall(alias)
        if quoted:
            return quoted[-1]
        # Bare alias: take first identifier token
        m = re.match(r'([A-Za-z_][A-Za-z0-9_]*)', alias)
        return m.group(1) if m else ""
    # No AS — trailing backticked identifier, else last referenced column
    quoted = _QUOTED_IDENT_RE.findall(item)
    if quoted:
        return quoted[-1]
    cols = _referenced_columns(item)
    return cols[-1] if cols else ""


def _unwrap_outer_select_star(sql: str) -> str:
    """Peel ``SELECT * FROM (inner) …`` wrappers so projection names are visible.

    Map top-N unpivot wraps the UNION in an outer SELECT *; without unwrapping,
    projected-output checks would see no named columns.
    """
    current = (sql or "").strip()
    for _ in range(4):  # bound peel depth
        select_spans = _top_level_spans(current, _SELECT_RE)
        from_spans = _top_level_spans(current, _FROM_RE)
        if not select_spans or not from_spans:
            return current
        sel_end = select_spans[0][1]
        from_start = next((s for s, _ in from_spans if s > sel_end), None)
        if from_start is None:
            return current
        items = _split_top_level(current[sel_end:from_start], _COMMA_RE)
        if not (len(items) == 1 and items[0] == "*"):
            return current
        after_from = current[from_spans[0][1]:].lstrip()
        if not after_from.startswith("("):
            return current
        depth = 0
        end = None
        for i, ch in enumerate(after_from):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            return current
        current = after_from[1:end].strip()
    return current


def _projected_output_columns(sql: str) -> set:
    """Output column names of a dataset query (intersection across UNION branches).

    Unlike scanning every backtick in the SQL, this only returns columns that
    appear in the SELECT projection — so ``SUM(`Total_Incidents`)`` inside a
    UNION branch that aliases to ``Value`` does NOT make ``Total_Incidents``
    look like an available output column.
    """
    if not (sql or "").strip():
        return set()
    sql = _unwrap_outer_select_star(sql)
    branch_outputs: List[set] = []
    for branch in _split_top_level(sql, _SET_OP_RE):
        select_spans = _top_level_spans(branch, _SELECT_RE)
        from_spans = _top_level_spans(branch, _FROM_RE)
        if not select_spans or not from_spans:
            continue
        sel_end = select_spans[0][1]
        from_start = next((s for s, _ in from_spans if s > sel_end), None)
        if from_start is None:
            continue
        names: set = set()
        for item in _split_top_level(branch[sel_end:from_start], _COMMA_RE):
            name = _select_item_output_name(item)
            if name:
                names.add(name)
        if names:
            branch_outputs.append(names)
    if not branch_outputs:
        return set()
    # Intersection: a widget may only rely on columns present in every branch
    out = set(branch_outputs[0])
    for s in branch_outputs[1:]:
        out &= s
    return out


def _field_binds_to_projection(
    fname: str,
    expr: str,
    output_cols: set,
) -> bool:
    """True when a widget query field is satisfiable from dataset output columns."""
    if not fname:
        return True
    if fname in output_cols:
        return True
    if _make_safe_alias_local(fname) in output_cols:
        return True
    if any(_make_safe_alias_local(c) == fname for c in output_cols):
        return True
    # Derived alias (e.g. 'sum(Value)' over SUM(`Value`)): only inputs must exist
    expr_idents = set(_QUOTED_IDENT_RE.findall(expr or ""))
    if expr_idents and all(
        (i in output_cols) or (_make_safe_alias_local(i) in output_cols)
        for i in expr_idents
    ):
        return True
    return False


def validate_lakeview_dashboard(lakeview_dash: LakeviewDashboard) -> Dict[str, Any]:
    """
    Stage 9 6-Tier Validation Engine:
    1. Schema Validation (jsonschema vs 24_json_schema.json)
    2. SQL Validation (sqlglot Spark dialect)
    3. Reference Integrity Validation (widget query datasetName in datasets)
    4. Layout Bounds & Collision Validation (6-col grid bounds)
    5. Widget Spec Validation (version & widgetType checks)
    6. ID Uniqueness & Cycle Validation
    """
    dash_dict = lakeview_dash.to_dict(allow_incomplete=True)
    errors = []
    warnings = []

    # Tier 1: JSON Schema Validation
    if jsonschema is not None and os.path.exists(SCHEMA_FILE):
        try:
            with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
                schema_json = json.load(f)
            jsonschema.validate(instance=dash_dict, schema=schema_json)
        except jsonschema.ValidationError as ve:
            errors.append(f"Schema Validation Error: {ve.message}")
        except Exception as e:
            warnings.append(f"Schema Validation Warning: {str(e)}")

    # Tier 2: SQL Validation
    dataset_ids = set()
    for ds in lakeview_dash.datasets:
        dataset_ids.add(ds.name)
        if not ds.query:
            errors.append(f"Dataset '{ds.displayName}' has empty query.")
        elif sqlglot is not None:
            try:
                sqlglot.parse_one(ds.query, read="spark")
            except Exception as se:
                warnings.append(f"SQL Syntax Warning in dataset '{ds.displayName}': {str(se)}")

    # Tier 3: Reference Integrity — check that widget queries reference valid datasets
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            widget = layout_item.widget
            if widget.queries:
                for q in widget.queries:
                    ds_ref = q.query.get("datasetName", "")
                    if ds_ref and ds_ref not in dataset_ids:
                        errors.append(
                            f"Widget '{widget.name}' references non-existent dataset '{ds_ref}'."
                        )

    # Tier 4: Layout Grid Validation
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            pos = layout_item.position
            if pos.x < 0 or pos.x > 5:
                errors.append(f"Widget '{layout_item.widget.name}' position x={pos.x} out of grid range (0..5).")
            if pos.width < 1 or pos.width > 6:
                errors.append(f"Widget '{layout_item.widget.name}' position width={pos.width} out of grid range (1..6).")
            if pos.x + pos.width > 6:
                errors.append(
                    f"Widget '{layout_item.widget.name}' exceeds 6-column boundary: "
                    f"x={pos.x} + width={pos.width} = {pos.x + pos.width} > 6."
                )
            if pos.height < 1:
                errors.append(f"Widget '{layout_item.widget.name}' height must be >= 1.")

    # Tier 5: Widget Spec Validation
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            widget = layout_item.widget
            if not widget.spec and not widget.is_text_widget:
                errors.append(f"Widget '{widget.name}' must have either spec or textbox_spec.")
            elif widget.spec:
                ok, spec_errors = validate_widget_spec(widget.spec)
                if not ok:
                    for se in spec_errors:
                        errors.append(f"Widget '{widget.name}' renderSpec invalid: {se}")

    # Tier 6: ID Uniqueness
    all_widget_ids = []
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            all_widget_ids.append(layout_item.widget.name)
    if len(all_widget_ids) != len(set(all_widget_ids)):
        errors.append("Duplicate widget IDs detected.")

    # Tier 7: Datasource Resolution — flag unresolved table references
    for ds in lakeview_dash.datasets:
        if ds.query and UNRESOLVED_TABLE_RE.search(ds.query):
            match = UNRESOLVED_TABLE_RE.search(ds.query)
            msg = f"Dataset '{ds.displayName}' contains unmapped table reference '{match.group().strip()}'."
            errors.append(msg)
            warnings.append(
                f"{msg} On Unity Catalog clusters, provide a table_mapping (e.g. catalog.schema.table)."
            )

    # Tier 8: Pseudo-Field Detection — reject Tableau-only fields in SQL
    for ds in lakeview_dash.datasets:
        if not ds.query:
            continue
        for pattern in PSEUDO_FIELD_PATTERNS:
            m = pattern.search(ds.query)
            if m:
                errors.append(
                    f"Dataset '{ds.displayName}' contains Tableau pseudo-field '{m.group()}' "
                    f"which does not exist in real data."
                )
        if TABLEAU_INTERNAL_RE.search(ds.query):
            m = TABLEAU_INTERNAL_RE.search(ds.query)
            errors.append(
                f"Dataset '{ds.displayName}' contains Tableau internal reference '{m.group()}'."
            )

    # Tier 9: Widget Spec Compatibility — validate widgetType
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            widget = layout_item.widget
            if widget.spec:
                wt = widget.spec.get("widgetType", "")
                if wt and wt not in SUPPORTED_WIDGET_TYPES:
                    warnings.append(
                        f"Widget '{widget.name}' uses unsupported widgetType '{wt}'. "
                        f"May cause specLoadError in Databricks."
                    )

    # Tier 10: Filter Sanity — reject Tableau internal IDs in filter values
    for ds in lakeview_dash.datasets:
        if not ds.query:
            continue
        if TABLEAU_INTERNAL_RE.search(ds.query):
            m = TABLEAU_INTERNAL_RE.search(ds.query)
            errors.append(
                f"Dataset '{ds.displayName}' SQL contains Tableau internal filter value '{m.group()}'."
            )

    # P2.1: Tier 11 — Encoding-Field Binding Validation
    # Ensures every spec.encodings.*.fieldName matches a query.fields[].name
    PLACEHOLDER_FIELDS = {'x', 'y', 'value', 'filter_col', 'X', 'Y', 'Value', '0', ''}
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            widget = layout_item.widget
            if not widget.spec or not widget.queries:
                continue

            # Collect all field names from widget queries
            query_field_names = set()
            for q in widget.queries:
                for field in q.query.get("fields", []):
                    query_field_names.add(field.get("name", ""))

            # Check encoding fieldNames against query fields — ERROR for charts
            encodings = widget.spec.get("encodings", {})
            wt = widget.spec.get("widgetType", "")
            CHART_TYPES_FOR_BINDING = {
                'bar', 'line', 'area', 'scatter', 'pie', 'counter',
                'heatmap', 'histogram',
            }
            for channel_key in ('x', 'y', 'color', 'value', 'angle'):
                channel = encodings.get(channel_key)
                if channel and isinstance(channel, dict):
                    field_name = channel.get("fieldName", "")
                    if field_name and field_name not in query_field_names and query_field_names:
                        msg = (
                            f"Widget '{widget.name}' encoding channel '{channel_key}' references "
                            f"field '{field_name}' which is not in query fields: {query_field_names}."
                        )
                        if wt in CHART_TYPES_FOR_BINDING:
                            errors.append(msg)
                        else:
                            warnings.append(msg)

    # P2.2: Tier 12 — Widget Completeness Validation
    CHART_WIDGET_TYPES = {'bar', 'line', 'area', 'scatter', 'pie', 'counter'}
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            widget = layout_item.widget
            if widget.is_text_widget:
                continue  # Text widgets are always valid

            wt = (widget.spec or {}).get("widgetType", "") if widget.spec else ""

            # Check for empty query fields — ERROR for chart widgets
            if widget.queries:
                for q in widget.queries:
                    fields = q.query.get("fields", [])
                    if not fields:
                        msg = (
                            f"Widget '{widget.name}' has empty query fields list — may render blank."
                        )
                        if wt in CHART_WIDGET_TYPES:
                            errors.append(msg)
                        else:
                            warnings.append(msg)

            # Check for placeholder fieldNames in encodings
            if widget.spec:
                encodings = widget.spec.get("encodings", {})
                for channel_key in ('x', 'y', 'value'):
                    channel = encodings.get(channel_key)
                    if channel and isinstance(channel, dict):
                        fn = channel.get("fieldName", "")
                        if fn in PLACEHOLDER_FIELDS:
                            errors.append(
                                f"Widget '{widget.name}' has placeholder fieldName '{fn}' in "
                                f"'{channel_key}' encoding — will render blank in Databricks."
                            )

                # Completeness for chart encodings (scale.type + required channels)
                if wt == 'pie':
                    if 'x' in encodings or 'y' in encodings:
                        errors.append(
                            f"Widget '{widget.name}' (pie) must not use x/y encodings — use angle/color."
                        )
                    for ch_name in ('angle', 'color'):
                        ch = encodings.get(ch_name) if isinstance(encodings.get(ch_name), dict) else None
                        if not ch or not ch.get('fieldName'):
                            errors.append(
                                f"Widget '{widget.name}' (pie) missing required '{ch_name}' encoding fieldName."
                            )
                        elif not (ch.get('scale') or {}).get('type'):
                            errors.append(
                                f"Widget '{widget.name}' (pie) '{ch_name}' encoding missing scale.type."
                            )
                elif wt in ('bar', 'scatter', 'line', 'area', 'histogram'):
                    x_ch = encodings.get('x') if isinstance(encodings.get('x'), dict) else None
                    y_ch = encodings.get('y') if isinstance(encodings.get('y'), dict) else None
                    if not x_ch or not x_ch.get('fieldName'):
                        errors.append(
                            f"Widget '{widget.name}' ({wt}) missing required 'x' encoding fieldName."
                        )
                    elif not (x_ch.get('scale') or {}).get('type'):
                        errors.append(
                            f"Widget '{widget.name}' ({wt}) 'x' encoding missing scale.type."
                        )
                    if not y_ch or not y_ch.get('fieldName'):
                        errors.append(
                            f"Widget '{widget.name}' ({wt}) missing required 'y' encoding fieldName."
                        )
                    elif not (y_ch.get('scale') or {}).get('type'):
                        errors.append(
                            f"Widget '{widget.name}' ({wt}) 'y' encoding missing scale.type."
                        )
                    elif (
                        x_ch and y_ch
                        and x_ch.get('fieldName')
                        and y_ch.get('fieldName')
                        and x_ch.get('fieldName') == y_ch.get('fieldName')
                    ):
                        errors.append(
                            f"Widget '{widget.name}' ({wt}) binds both x and y to identical field "
                            f"'{x_ch.get('fieldName')}'."
                        )
                elif wt == 'heatmap':
                    for ch_name in ('x', 'y', 'color'):
                        ch = encodings.get(ch_name) if isinstance(encodings.get(ch_name), dict) else None
                        if not ch or not ch.get('fieldName'):
                            errors.append(
                                f"Widget '{widget.name}' (heatmap) missing required '{ch_name}' encoding."
                            )
                        elif not (ch.get('scale') or {}).get('type'):
                            errors.append(
                                f"Widget '{widget.name}' (heatmap) '{ch_name}' encoding missing scale.type."
                            )

                # Empty encodings object is always an error for viz widgets
                if wt in CHART_WIDGET_TYPES | {'heatmap', 'histogram', 'table'} and not encodings:
                    errors.append(
                        f"Widget '{widget.name}' ({wt}) has empty encodings — will fail Databricks renderer."
                    )

                # Check for empty table columns
                if wt == "table":
                    cols = encodings.get("columns", [])
                    if not cols:
                        warnings.append(
                            f"Widget '{widget.name}' (table) has empty columns list — will render blank."
                        )

                # Orphaned widgets: no queries at all
                if wt in CHART_WIDGET_TYPES | {'heatmap', 'histogram', 'table'} and not widget.queries:
                    errors.append(
                        f"Widget '{widget.name}' ({wt}) has no queries — orphaned from any dataset."
                    )

    # Tier 12: SQL Aggregation & GROUP BY Validation
    for ds in lakeview_dash.datasets:
        if not ds.query:
            continue
        for col_name in _unaggregated_columns(ds.query):
            errors.append(
                f"Dataset '{ds.displayName}' contains MISSING_AGGREGATION error: "
                f"column '{col_name}' is not aggregated and not in GROUP BY."
            )

    # Tier 12b — Dataset SQL incompleteness / binding subset mismatch
    ds_by_name = {ds.name: ds for ds in lakeview_dash.datasets}
    for page in lakeview_dash.pages:
        for layout_item in page.layout:
            widget = layout_item.widget
            if not widget.queries:
                continue
            for q in widget.queries:
                ds_name = q.query.get("datasetName")
                ds = ds_by_name.get(ds_name) if ds_name else None
                if not ds or not ds.query:
                    continue
                if "__incomplete_projection__" in ds.query:
                    errors.append(
                        f"Widget '{widget.name}' references dataset with incomplete SQL projection "
                        f"(no real fields resolved from shelves/encodings)."
                    )
                # Binding mismatch: widget fields must resolve to *projected*
                # output columns (not identifiers merely referenced inside
                # SUM/WHERE of a UNION branch). Escalate to errors — this is a
                # guaranteed query-time column-not-found failure.
                output_cols = _projected_output_columns(ds.query)
                for field in q.query.get("fields", []):
                    fname = field.get("name", "")
                    expr = field.get("expression", "") or ""
                    if not fname or fname in ("x", "y", "value", "filter_col", "X", "Y", "Value", "0", '""'):
                        continue
                    if _field_binds_to_projection(fname, expr, output_cols):
                        continue
                    errors.append(
                        f"Widget '{widget.name}' field '{fname}' not found in dataset "
                        f"output columns {sorted(output_cols)[:12]} "
                        f"(dataset '{ds.displayName}')."
                    )

    # P2.2: Tier 13 — Layout Density Validation
    for page in lakeview_dash.pages:
        if not page.layout:
            continue
        all_width_one = all(
            layout_item.position.width == 1
            for layout_item in page.layout
            if not layout_item.widget.is_text_widget
        )
        if all_width_one and len(page.layout) > 2:
            warnings.append(
                f"Page '{page.displayName}' has all non-text widgets with width=1 — "
                f"dashboard will appear squeezed. Consider wider widget layouts."
            )

    is_valid = len(errors) == 0
    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "tier_status": {
            "schema_validation": not any("Schema" in e for e in errors),
            "sql_validation": not any("SQL" in e for e in errors),
            "reference_validation": not any("references" in e for e in errors),
            "layout_validation": not any("boundary" in e or "grid" in e for e in errors),
            "widget_validation": not any("spec" in e for e in errors),
            "integrity_validation": not any("Duplicate" in e for e in errors),
            "datasource_resolution": not any("unresolved table" in e.lower() for e in errors),
            "pseudo_field_detection": not any("pseudo-field" in e.lower() for e in errors),
            "widget_spec_compat": not any("specLoadError" in e for e in warnings),
            "filter_sanity": not any("internal filter" in e.lower() for e in errors),
            "encoding_field_binding": not any("encoding channel" in e.lower() for e in errors + warnings),
            "widget_completeness": not any(
                ("placeholder fieldName" in e)
                or ("empty query fields" in e)
                or ("empty encodings" in e)
                or ("missing required" in e)
                or ("incomplete SQL projection" in e)
                or ("identical field" in e)
                or ("has no queries" in e)
                for e in errors
            ),
            "layout_density": not any("width=1" in w for w in warnings),
        }
    }


_INCOMPLETE_CHART_TYPES = {
    "bar", "line", "area", "scatter", "pie", "counter", "heatmap", "histogram", "table",
}


def _widget_is_incomplete_chart(widget) -> bool:
    """True when a viz widget would render blank (empty encodings / queries / fields)."""
    if widget.is_text_widget:
        return False
    if not widget.spec:
        return True
    wt = widget.spec.get("widgetType", "")
    if wt not in _INCOMPLETE_CHART_TYPES and not (wt or "").startswith("filter-"):
        return False
    encodings = widget.spec.get("encodings") or {}
    if not encodings:
        return True
    if not widget.queries:
        return True
    for q in widget.queries:
        if not (q.query or {}).get("fields"):
            return True
    ok, _ = validate_widget_spec(widget.spec)
    return not ok


def prune_incomplete_widgets(lakeview_dash: LakeviewDashboard) -> List[str]:
    """Remove chart widgets that would serialize as blank shells. Returns removed titles/ids."""
    removed: List[str] = []
    for page in lakeview_dash.pages:
        kept = []
        for item in page.layout:
            if _widget_is_incomplete_chart(item.widget):
                title = ((item.widget.spec or {}).get("frame") or {}).get("title") or item.widget.name
                removed.append(title)
            else:
                kept.append(item)
        page.layout = kept
    return removed

