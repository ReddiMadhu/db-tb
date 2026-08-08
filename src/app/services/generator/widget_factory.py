"""
widget_factory.py — Centralized Databricks AI/BI Widget Schema Factory
======================================================================
Single source of truth for constructing Databricks Lakeview AI/BI widgets.
Guarantees schema-version compliance, required encodings (scale.type),
valid queries & fields, and prevents schema drift across the repository.

Version rules (verified against Lakeview serialized schema):
  - Charts (bar/line/area/scatter/pie/heatmap/histogram/combo): version 3
  - Counter / filters: version 2
  - Table: version 1 (official NYC Taxi sample + schema docs)
  - Pivot: version 3 with cubeGroupingSets + orders (live-verified)

Encoding rules:
  - Bar / Line / Area: x + y (+ optional color); every channel has scale.type
  - Pie: color + angle (NEVER x/y)
  - Scatter: x + y (quantitative)
  - Heatmap: x + y + color
  - Histogram: x + y
  - Table: encodings.columns
  - Counter: encodings.value
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.lakeview_model import Widget, WidgetQuery, generate_lakeview_id

DEFAULT_COLORS = [
    "#077A9D", "#FFAB00", "#00A972", "#FF3621", "#8BCAE7",
    "#AB4057", "#99DDB4", "#FCA4A1", "#919191", "#BF7080",
]

# Stub axis names used when bindings are incomplete — NOT real dataset columns.
# Do NOT include "Value" / "Metric": those are legitimate unpivot output columns.
PLACEHOLDER_FIELDS = {"x", "y", "value", "filter_col", "X", "Y", "0", ""}

# Chart widgetTypes that require version 3
CHART_TYPES_V3 = {
    "bar", "line", "area", "scatter", "pie",
    "heatmap", "histogram", "boxplot", "map",
}

# Chart widgetTypes that require version 1
CHART_TYPES_V1 = {"table", "combo", "pivot", "funnel", "sankey"}

# Canonical mapping of widgetType to expected Lakeview schema version
WIDGET_VERSION: Dict[str, int] = {
    "bar": 3, "line": 3, "area": 3, "scatter": 3, "pie": 3,
    "heatmap": 3, "histogram": 3, "boxplot": 3, "map": 3,
    "choropleth-map": 3, "symbol-map": 3,
    "counter": 2,
    "filter-multi-select": 2, "filter-single-select": 2,
    "filter-date-range-picker": 2, "filter-date-picker": 2,
    "table": 1, "combo": 1, "pivot": 3, "funnel": 1, "sankey": 1,
}

TEMPORAL_HINTS = re.compile(
    r"(date|time|month|year|week|day|timestamp|datetime|period|dt_)",
    re.IGNORECASE,
)


def _clean_title(name: str) -> str:
    """Format field name to clean title (e.g. Total_Claim -> Total Claim)."""
    if not name:
        return ""
    return name.replace("_", " ").strip().title()


def _frame(title: str, show_title: bool = True, fallback: str = "", **extra) -> Dict[str, Any]:
    """Build Lakeview frame dict. Blank/hidden titles must not invent fallback text."""
    if not show_title:
        frame: Dict[str, Any] = {"title": "", "showTitle": False}
    else:
        frame = {"title": (title or fallback or ""), "showTitle": True}
    frame.update(extra)
    return frame


def infer_scale_type(
    field_name: str,
    *,
    role: str = "dimension",
    explicit: Optional[str] = None,
    datatype: Optional[str] = None,
) -> str:
    """Infer Lakeview scale.type for an encoding channel.

    Temporal requires a date-like datatype (or explicit). Name hints alone
    (e.g. Effective_Year) must not force temporal when the column is integer
    or a non-date string/categorical.
    """
    if explicit in ("quantitative", "temporal", "categorical", "ordinal"):
        return explicit
    if role == "measure":
        return "quantitative"
    dt = (datatype or "").lower().strip()
    date_like = dt in (
        "date", "datetime", "timestamp", "timestamptz", "time",
    )
    numeric_like = dt in (
        "integer", "int", "long", "real", "float", "double", "number",
        "bigint", "smallint", "tinyint", "decimal", "numeric",
    )
    if date_like:
        return "temporal"
    if numeric_like:
        # Integer years / ids stay categorical on axes unless role=measure
        return "categorical"
    # Name-based temporal only when datatype is unknown/string-like and looks like a real date field
    if field_name and TEMPORAL_HINTS.search(field_name):
        # "year" / "month" alone as integer-named dims are categorical when no date type
        if re.search(r"(^|_)(year|month|week|day|period)(_|$)", field_name, re.IGNORECASE):
            if not dt or dt in ("string", "str", "varchar", "text", ""):
                # Ambiguous — prefer categorical for year/month token fields
                if re.search(r"year|month|week|day|period", field_name, re.IGNORECASE) and not re.search(
                    r"date|time|timestamp|datetime", field_name, re.IGNORECASE
                ):
                    return "categorical"
        if re.search(r"date|time|timestamp|datetime", field_name, re.IGNORECASE):
            return "temporal"
    return "categorical"


def sanitize_query_fields(fields: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Sanitize query field list to ensure no nulls or empty field definitions."""
    sanitized: List[Dict[str, str]] = []
    seen = set()
    for f in fields:
        name = (f.get("name") or "").strip()
        expr = (f.get("expression") or "").strip()
        if not name or name in PLACEHOLDER_FIELDS:
            continue
        if name in seen:
            continue
        seen.add(name)
        sanitized.append({
            "expression": expr or f"`{name}`",
            "name": name,
        })
    return sanitized


def _axis_encoding(
    field_name: str,
    scale_type: str,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    title = display_name or _clean_title(field_name)
    return {
        "fieldName": field_name,
        "displayName": title,
        "scale": {"type": scale_type},
        "axis": {"title": title},
    }


def _channel_encoding(
    field_name: str,
    scale_type: str,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    title = display_name or _clean_title(field_name)
    return {
        "fieldName": field_name,
        "displayName": title,
        "scale": {"type": scale_type},
    }


def validate_widget_spec(spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a renderSpec / widget.spec object against Databricks AI/BI rules."""
    errors: List[str] = []
    if not spec:
        return False, ["Widget spec is missing or null."]

    v = spec.get("version")
    wt = spec.get("widgetType")
    if not wt:
        errors.append("Missing required 'widgetType' in spec.")
        return False, errors

    if wt in CHART_TYPES_V3 and v != 3:
        errors.append(f"Chart widgetType '{wt}' requires version 3, got {v}.")
    elif wt == "combo" and v != 1:
        errors.append(f"Combo widget requires version 1, got {v}.")
    elif wt == "counter" and v != 2:
        errors.append(f"Counter widget requires version 2, got {v}.")
    elif wt and wt.startswith("filter-") and v != 2:
        errors.append(f"Filter widget '{wt}' requires version 2, got {v}.")
    elif wt == "table" and v != 1:
        errors.append(f"Table widget requires version 1, got {v}.")
    elif wt == "pivot" and v != 3:
        errors.append(f"Pivot widget requires version 3, got {v}.")
    elif v not in (1, 2, 3):
        errors.append(f"Invalid widget spec version '{v}'.")

    encodings = spec.get("encodings", {})
    if not isinstance(encodings, dict):
        errors.append("Invalid 'encodings' structure — must be an object.")
        return False, errors

    if not encodings and wt not in ("",):
        errors.append(f"Widget '{wt}' has empty encodings object.")

    def _require_channels(channels: Tuple[str, ...], require_scale: bool = True) -> None:
        for ch_name in channels:
            ch = encodings.get(ch_name)
            if not isinstance(ch, dict) or not ch.get("fieldName"):
                errors.append(f"{wt} missing required '{ch_name}' encoding fieldName.")
            elif require_scale and not (ch.get("scale") or {}).get("type"):
                errors.append(f"{wt} '{ch_name}' encoding missing scale.type.")

    if wt == "bar":
        _require_channels(("x", "y"))
        x_fn = (encodings.get("x") or {}).get("fieldName")
        y_fn = (encodings.get("y") or {}).get("fieldName")
        if x_fn and y_fn and x_fn == y_fn:
            errors.append(f"Bar chart binds x and y to identical field '{x_fn}'.")
        if "x" in encodings or "y" in encodings:
            color = encodings.get("color")
            if isinstance(color, dict) and color.get("fieldName") and not (color.get("scale") or {}).get("type"):
                errors.append("Bar chart 'color' encoding missing scale.type.")

    elif wt == "pie":
        if "x" in encodings or "y" in encodings:
            errors.append("Pie chart must NOT use 'x' or 'y' encodings — use 'angle' and 'color'.")
        _require_channels(("angle", "color"))

    elif wt in ("line", "area"):
        _require_channels(("x", "y"))
        x_fn = (encodings.get("x") or {}).get("fieldName")
        y_fn = (encodings.get("y") or {}).get("fieldName")
        if x_fn and y_fn and x_fn == y_fn:
            errors.append(f"{wt} chart binds x and y to identical field '{x_fn}'.")

    elif wt == "scatter":
        _require_channels(("x", "y"))
        x_fn = (encodings.get("x") or {}).get("fieldName")
        y_fn = (encodings.get("y") or {}).get("fieldName")
        if x_fn and y_fn and x_fn == y_fn:
            errors.append(f"Scatter binds x and y to identical field '{x_fn}'.")

    elif wt == "heatmap":
        _require_channels(("x", "y", "color"))

    elif wt == "histogram":
        _require_channels(("x", "y"))

    elif wt == "combo":
        _require_channels(("x",))
        y = encodings.get("y")
        if not isinstance(y, dict):
            errors.append("combo missing required 'y' encoding.")
        else:
            has_top_level = bool(y.get("fieldName"))
            has_primary = isinstance(y.get("primary"), dict)
            if not has_top_level and not has_primary:
                errors.append("combo 'y' encoding must have either 'fieldName' or 'primary' structure.")

    elif wt == "table":
        cols = encodings.get("columns")
        if not isinstance(cols, list) or not cols:
            errors.append("Table widget missing required 'columns' encodings list.")

    elif wt == "pivot":
        rows = encodings.get("rows")
        cols = encodings.get("columns")
        cell = encodings.get("cell")
        if not isinstance(rows, list) or not rows:
            errors.append("Pivot widget missing required 'rows' encodings list.")
        if not isinstance(cols, list) or not cols:
            errors.append("Pivot widget missing required 'columns' encodings list.")
        if not isinstance(cell, dict) or not cell.get("fieldName"):
            errors.append("Pivot widget missing required 'cell' encoding fieldName.")

    elif wt == "counter":
        value = encodings.get("value")
        if not isinstance(value, dict) or not value.get("fieldName"):
            errors.append("Counter widget missing required 'value' encoding fieldName.")

    elif wt and wt.startswith("filter-"):
        fields = encodings.get("fields")
        if not isinstance(fields, list) or not fields:
            errors.append(f"Filter widget '{wt}' missing required 'fields' encodings list.")

    return len(errors) == 0, errors


class WidgetFactory:
    """Centralized Factory for building Databricks AI/BI widgets."""

    @staticmethod
    def _create_widget_query(
        dataset_name: str,
        fields: List[Dict[str, str]],
        disaggregated: bool = False,
        query_name: str = "main_query",
    ) -> WidgetQuery:
        clean_fields = sanitize_query_fields(fields)
        return WidgetQuery(
            name=query_name,
            query={
                "datasetName": dataset_name,
                "disaggregated": disaggregated,
                "disaggregatedData": disaggregated,
                "fields": clean_fields,
            },
        )

    @staticmethod
    def _ensure_field(
        qfields: List[Dict[str, str]],
        name: str,
        expression: Optional[str] = None,
    ) -> None:
        if not name or any(f.get("name") == name for f in qfields):
            return
        qfields.append({
            "expression": expression or f"`{name}`",
            "name": name,
        })

    @classmethod
    def create_bar_widget(
        cls,
        dataset_name: str,
        x_field: str,
        y_field: str,
        title: str = "",
        color_field: Optional[str] = None,
        query_fields: Optional[List[Dict[str, str]]] = None,
        x_scale_type: str = "categorical",
        y_scale_type: str = "quantitative",
        properties: Optional[Dict[str, Any]] = None,
        show_title: bool = True,
    ) -> Widget:
        """Create a Version 3 Bar Chart widget."""
        if x_field == y_field:
            raise ValueError(
                f"Bar chart requires distinct x/y fields; got identical '{x_field}'."
            )
        qfields = list(query_fields) if query_fields else []
        if not qfields:
            qfields = [
                {"expression": f"`{x_field}`", "name": x_field},
                {"expression": f"SUM(`{y_field}`)", "name": y_field},
            ]
        cls._ensure_field(qfields, x_field)
        cls._ensure_field(qfields, y_field, f"SUM(`{y_field}`)")
        if color_field:
            cls._ensure_field(qfields, color_field)

        props = properties or {}
        axes_list = props.get("axes", [])
        x_axis_meta = next((a for a in axes_list if a.get("shelf") == "columns" or a.get("field_name") == x_field), {})
        y_axis_meta = next((a for a in axes_list if a.get("shelf") == "rows" or a.get("field_name") == y_field), {})

        x_title = x_axis_meta.get("title") or _clean_title(x_field)
        y_title = y_axis_meta.get("title") or _clean_title(y_field)

        encodings: Dict[str, Any] = {
            "x": _axis_encoding(x_field, infer_scale_type(x_field, explicit=x_scale_type), display_name=x_title),
            "y": _axis_encoding(y_field, infer_scale_type(y_field, role="measure", explicit=y_scale_type), display_name=y_title),
            "label": {"show": False},
        }
        if x_axis_meta.get("logarithmic"):
            encodings["x"]["scale"]["type"] = "logarithmic"
        if y_axis_meta.get("logarithmic"):
            encodings["y"]["scale"]["type"] = "logarithmic"

        if color_field:
            encodings["color"] = _channel_encoding(color_field, "categorical")

        # Color palette override from mark_properties
        mark_props = props.get("mark_properties", [])
        color_prop = next((mp for mp in mark_props if mp.get("channel") == "color"), {})
        palette = color_prop.get("palette_colors") or DEFAULT_COLORS

        legend_list = props.get("legends", [])
        legend_meta = legend_list[0] if legend_list else {}
        legend_pos = legend_meta.get("position", "right")

        spec = {
            "version": 3,
            "widgetType": "bar",
            "encodings": encodings,
            "frame": _frame(
                title,
                show_title,
                fallback=_clean_title(y_field),
                legend={"position": legend_pos, "visible": not legend_meta.get("hidden", False)},
            ),
            "mark": {"colors": palette},
        }
        ok, errs = validate_widget_spec(spec)
        if not ok:
            raise ValueError(f"Invalid bar widget spec: {errs}")

        return Widget(queries=[cls._create_widget_query(dataset_name, qfields, False)], spec=spec)

    @classmethod
    def create_pie_widget(
        cls,
        dataset_name: str,
        category_field: str,
        value_field: str,
        title: str = "",
        query_fields: Optional[List[Dict[str, str]]] = None,
        show_title: bool = True,
    ) -> Widget:
        """Create a Version 3 Pie Chart widget (angle & color — NOT x & y)."""
        qfields = list(query_fields) if query_fields else [
            {"expression": f"`{category_field}`", "name": category_field},
            {"expression": f"SUM(`{value_field}`)", "name": value_field},
        ]
        cls._ensure_field(qfields, category_field)
        cls._ensure_field(qfields, value_field, f"SUM(`{value_field}`)")

        spec = {
            "version": 3,
            "widgetType": "pie",
            "encodings": {
                "color": _channel_encoding(category_field, "categorical"),
                "angle": _channel_encoding(value_field, "quantitative"),
            },
            "frame": _frame(
                title,
                show_title,
                fallback=f"{_clean_title(category_field)} Distribution",
            ),
            "mark": {"colors": DEFAULT_COLORS},
        }
        ok, errs = validate_widget_spec(spec)
        if not ok:
            raise ValueError(f"Invalid pie widget spec: {errs}")

        return Widget(queries=[cls._create_widget_query(dataset_name, qfields, False)], spec=spec)

    @classmethod
    def create_line_widget(
        cls,
        dataset_name: str,
        x_field: str,
        y_field: str,
        title: str = "",
        color_field: Optional[str] = None,
        is_area: bool = False,
        query_fields: Optional[List[Dict[str, str]]] = None,
        x_scale_type: Optional[str] = None,
        show_title: bool = True,
    ) -> Widget:
        """Create a Version 3 Line or Area Chart widget."""
        if x_field == y_field:
            raise ValueError(
                f"Line/Area chart requires distinct x/y fields; got identical '{x_field}'."
            )
        qfields = list(query_fields) if query_fields else [
            {"expression": f"`{x_field}`", "name": x_field},
            {"expression": f"SUM(`{y_field}`)", "name": y_field},
        ]
        cls._ensure_field(qfields, x_field)
        cls._ensure_field(qfields, y_field, f"SUM(`{y_field}`)")
        if color_field:
            cls._ensure_field(qfields, color_field)

        x_scale = infer_scale_type(x_field, explicit=x_scale_type)
        encodings: Dict[str, Any] = {
            "x": _axis_encoding(x_field, x_scale),
            "y": _axis_encoding(y_field, "quantitative"),
            "label": {"show": False},
        }
        if color_field:
            encodings["color"] = _channel_encoding(color_field, "categorical")

        widget_type = "area" if is_area else "line"
        spec = {
            "version": 3,
            "widgetType": widget_type,
            "encodings": encodings,
            "frame": _frame(title, show_title, fallback=_clean_title(y_field)),
            "mark": {"colors": DEFAULT_COLORS},
        }
        ok, errs = validate_widget_spec(spec)
        if not ok:
            raise ValueError(f"Invalid {widget_type} widget spec: {errs}")

        return Widget(queries=[cls._create_widget_query(dataset_name, qfields, False)], spec=spec)

    @classmethod
    def create_scatter_widget(
        cls,
        dataset_name: str,
        x_field: str,
        y_field: str,
        title: str = "",
        color_field: Optional[str] = None,
        query_fields: Optional[List[Dict[str, str]]] = None,
        show_title: bool = True,
    ) -> Widget:
        """Create a Version 3 Scatter Plot widget."""
        if x_field == y_field:
            raise ValueError(
                f"Scatter requires distinct x/y fields; got identical '{x_field}'."
            )
        qfields = list(query_fields) if query_fields else [
            {"expression": f"`{x_field}`", "name": x_field},
            {"expression": f"`{y_field}`", "name": y_field},
        ]
        cls._ensure_field(qfields, x_field)
        cls._ensure_field(qfields, y_field)
        if color_field:
            cls._ensure_field(qfields, color_field)

        encodings: Dict[str, Any] = {
            "x": _axis_encoding(x_field, "quantitative"),
            "y": _axis_encoding(y_field, "quantitative"),
        }
        if color_field:
            encodings["color"] = _channel_encoding(color_field, "categorical")

        spec = {
            "version": 3,
            "widgetType": "scatter",
            "encodings": encodings,
            "frame": _frame(
                title,
                show_title,
                fallback=f"{_clean_title(x_field)} vs {_clean_title(y_field)}",
            ),
            "mark": {"colors": DEFAULT_COLORS},
        }
        ok, errs = validate_widget_spec(spec)
        if not ok:
            raise ValueError(f"Invalid scatter widget spec: {errs}")

        return Widget(queries=[cls._create_widget_query(dataset_name, qfields, False)], spec=spec)

    @classmethod
    def create_heatmap_widget(
        cls,
        dataset_name: str,
        x_field: str,
        y_field: str,
        color_field: str,
        title: str = "",
        query_fields: Optional[List[Dict[str, str]]] = None,
        show_title: bool = True,
    ) -> Widget:
        """Create a Version 3 Heatmap widget (x, y, color)."""
        qfields = list(query_fields) if query_fields else [
            {"expression": f"`{x_field}`", "name": x_field},
            {"expression": f"`{y_field}`", "name": y_field},
            {"expression": f"SUM(`{color_field}`)", "name": color_field},
        ]
        cls._ensure_field(qfields, x_field)
        cls._ensure_field(qfields, y_field)
        cls._ensure_field(qfields, color_field, f"SUM(`{color_field}`)")

        spec = {
            "version": 3,
            "widgetType": "heatmap",
            "encodings": {
                "x": _axis_encoding(x_field, infer_scale_type(x_field)),
                "y": _axis_encoding(y_field, infer_scale_type(y_field)),
                "color": _channel_encoding(color_field, "quantitative"),
            },
            "frame": _frame(title, show_title, fallback=_clean_title(color_field)),
            "mark": {"colors": DEFAULT_COLORS},
        }
        ok, errs = validate_widget_spec(spec)
        if not ok:
            raise ValueError(f"Invalid heatmap widget spec: {errs}")

        return Widget(queries=[cls._create_widget_query(dataset_name, qfields, False)], spec=spec)

    @classmethod
    def create_histogram_widget(
        cls,
        dataset_name: str,
        x_field: str,
        y_field: str,
        title: str = "",
        query_fields: Optional[List[Dict[str, str]]] = None,
        show_title: bool = True,
    ) -> Widget:
        """Create a Version 3 Histogram widget."""
        qfields = list(query_fields) if query_fields else [
            {"expression": f"`{x_field}`", "name": x_field},
            {"expression": f"COUNT(*)", "name": y_field},
        ]
        cls._ensure_field(qfields, x_field)
        cls._ensure_field(qfields, y_field, "COUNT(*)")

        spec = {
            "version": 3,
            "widgetType": "histogram",
            "encodings": {
                "x": _axis_encoding(x_field, infer_scale_type(x_field)),
                "y": _axis_encoding(y_field, "quantitative"),
                "label": {"show": False},
            },
            "frame": _frame(
                title,
                show_title,
                fallback=f"{_clean_title(x_field)} Distribution",
            ),
            "mark": {"colors": DEFAULT_COLORS},
        }
        ok, errs = validate_widget_spec(spec)
        if not ok:
            raise ValueError(f"Invalid histogram widget spec: {errs}")

        return Widget(queries=[cls._create_widget_query(dataset_name, qfields, False)], spec=spec)

    @classmethod
    def create_table_widget(
        cls,
        dataset_name: str,
        column_fields: List[str],
        title: str = "",
        query_fields: Optional[List[Dict[str, str]]] = None,
        show_title: bool = True,
    ) -> Widget:
        """Create a Version 1 Table widget (Lakeview table schema is v1)."""
        qfields = list(query_fields) if query_fields else [
            {"expression": f"`{col}`", "name": col} for col in column_fields
        ]
        for col in column_fields:
            cls._ensure_field(qfields, col)

        columns_enc = []
        for i, col in enumerate(column_fields):
            # Infer type from matching query field expression when available
            col_type = "string"
            display_as = "string"
            for qf in qfields:
                if qf.get("name") == col:
                    expr = (qf.get("expression") or "").upper()
                    if expr.startswith(("SUM", "AVG", "COUNT", "MIN", "MAX", "PERCENTILE")):
                        col_type = "float"
                        display_as = "number"
                    break
            columns_enc.append({
                "fieldName": col,
                "displayName": _clean_title(col),
                "title": _clean_title(col),
                "type": col_type,
                "displayAs": display_as,
                "alignContent": "right" if display_as == "number" else "left",
                "visible": True,
                "order": 100000 + i,
            })

        spec = {
            "version": 1,
            "widgetType": "table",
            "encodings": {"columns": columns_enc},
            "frame": _frame(title, show_title, fallback="Table View"),
            "condensed": True,
            "itemsPerPage": 25,
        }
        ok, errs = validate_widget_spec(spec)
        if not ok:
            raise ValueError(f"Invalid table widget spec: {errs}")

        # Pre-aggregated measures → disaggregated=False; raw dims-only → True
        has_agg = any(
            (qf.get("expression") or "").upper().startswith(
                ("SUM", "AVG", "COUNT", "MIN", "MAX", "PERCENTILE")
            )
            for qf in qfields
        )
        return Widget(
            queries=[cls._create_widget_query(dataset_name, qfields, not has_agg)],
            spec=spec,
        )

    @classmethod
    def create_pivot_widget(
        cls,
        dataset_name: str,
        row_fields: List[str],
        column_fields: List[str],
        cell_field: str = "Value",
        title: str = "",
        query_fields: Optional[List[Dict[str, str]]] = None,
        show_title: bool = True,
        cell_expression: str = "`Value`",
    ) -> Widget:
        """Create a Version 3 Pivot widget over an unpivoted (Metric, Value) dataset.

        Live-verified Lakeview shape: version 3 with query-level cubeGroupingSets
        and orders (ASC on each row then column field). Measure Names → pivot
        must pass row_fields=['Metric'] and column_fields=[dim] with cell_field
        matching the Value aggregate alias.
        """
        qfields = list(query_fields) if query_fields else []
        for rf in row_fields:
            cls._ensure_field(qfields, rf, f"`{rf}`")
        for cf in column_fields:
            cls._ensure_field(qfields, cf, f"`{cf}`")
        cls._ensure_field(qfields, cell_field, cell_expression)

        rows_enc = [
            {"fieldName": rf, "scale": {"type": "categorical"}}
            for rf in row_fields
        ]
        cols_enc = [
            {"fieldName": cf, "scale": {"type": "categorical"}}
            for cf in column_fields
        ]

        cube_sets = (
            [{"fieldNames": list(row_fields)}] if row_fields else []
        ) + (
            [{"fieldNames": list(column_fields)}] if column_fields else []
        )
        orders = [
            {"direction": "ASC", "expression": f"`{f}`"}
            for f in list(row_fields) + list(column_fields)
        ]

        query_body: Dict[str, Any] = {
            "datasetName": dataset_name,
            "disaggregated": False,
            "disaggregatedData": False,
            "fields": sanitize_query_fields(qfields),
        }
        if cube_sets:
            query_body["cubeGroupingSets"] = {"sets": cube_sets}
        if orders:
            query_body["orders"] = orders

        spec = {
            "version": 3,
            "widgetType": "pivot",
            "encodings": {
                "rows": rows_enc,
                "columns": cols_enc,
                "cell": {
                    "type": "single-cell",
                    "fieldName": cell_field,
                    "format": {"type": "number-plain", "abbreviation": "compact"},
                },
            },
            "frame": _frame(title, show_title, fallback="Pivot View"),
            "data": {"queryName": "main_query"},
        }
        ok, errs = validate_widget_spec(spec)
        if not ok:
            raise ValueError(f"Invalid pivot widget spec: {errs}")

        return Widget(
            queries=[WidgetQuery(name="main_query", query=query_body)],
            spec=spec,
        )

    @classmethod
    def create_counter_widget(
        cls,
        dataset_name: str,
        value_field: str,
        title: str = "",
        query_fields: Optional[List[Dict[str, str]]] = None,
        show_title: bool = True,
    ) -> Widget:
        """Create a Version 2 Counter / KPI widget."""
        qfields = list(query_fields) if query_fields else [
            {"expression": f"`{value_field}`", "name": value_field},
        ]
        # Prefer passthrough of dataset output alias (dataset owns aggregation)
        cls._ensure_field(qfields, value_field, f"`{value_field}`")

        spec = {
            "version": 2,
            "widgetType": "counter",
            "encodings": {
                "value": {
                    "fieldName": value_field,
                    "displayName": title or _clean_title(value_field),
                }
            },
            "frame": _frame(title, show_title, fallback=_clean_title(value_field)),
        }
        ok, errs = validate_widget_spec(spec)
        if not ok:
            raise ValueError(f"Invalid counter widget spec: {errs}")

        return Widget(queries=[cls._create_widget_query(dataset_name, qfields, False)], spec=spec)

    @classmethod
    def create_filter_widget(
        cls,
        dataset_name: str,
        field_name: str,
        title: str = "",
        filter_type: str = "filter-multi-select",
        query_fields: Optional[List[Dict[str, str]]] = None,
        show_title: bool = True,
        dashboard_id: Optional[str] = None,
        query_name: Optional[str] = None,
    ) -> Widget:
        """Create a Version 2 Filter widget.

        ``queryName`` in encodings must equal the widget query ``name``.
        Always use a local query name (default ``main_query``); never an
        external ``dashboards/.../datasets/...`` path.
        """
        allowed = {
            "filter-multi-select",
            "filter-single-select",
            "filter-date-range-picker",
            "filter-date-picker",
        }
        if filter_type not in allowed:
            filter_type = "filter-multi-select"

        qfields = list(query_fields) if query_fields else [
            {"expression": f"`{field_name}`", "name": field_name},
        ]
        cls._ensure_field(qfields, field_name)

        qname = query_name or "main_query"
        if "/" in qname or qname.startswith("dashboards/"):
            qname = "main_query"

        spec = {
            "version": 2,
            "widgetType": filter_type,
            "encodings": {
                "fields": [
                    {
                        "fieldName": field_name,
                        "displayName": _clean_title(field_name),
                        "queryName": qname,
                    }
                ]
            },
            "frame": _frame(title, show_title, fallback=_clean_title(field_name)),
        }
        ok, errs = validate_widget_spec(spec)
        if not ok:
            raise ValueError(f"Invalid filter widget spec: {errs}")

        return Widget(
            queries=[cls._create_widget_query(dataset_name, qfields, True, query_name=qname)],
            spec=spec,
        )

    @classmethod
    def create_combo_widget(
        cls,
        dataset_name: str,
        x_field: str,
        y_fields: List[Dict[str, str]],
        title: str = "",
        color_field: Optional[str] = None,
        query_fields: Optional[List[Dict[str, str]]] = None,
        show_title: bool = True,
        enable_dual_axis: bool = True,
    ) -> Widget:
        """Create a Version 1 Combo Chart widget (bar+line dual-axis)."""
        qfields = list(query_fields) if query_fields else []
        cls._ensure_field(qfields, x_field)
        for yf in y_fields:
            fname = yf.get("field") or yf.get("fieldName") or ""
            if fname:
                fallback_expr = f"SUM(`{fname}`)" if not query_fields else f"`{fname}`"
                cls._ensure_field(qfields, fname, fallback_expr)

        primary_fname = ""
        secondary_fname = ""
        if y_fields:
            primary_fname = y_fields[0].get("field") or y_fields[0].get("fieldName") or ""
            if primary_fname:
                fallback_expr = f"SUM(`{primary_fname}`)" if not query_fields else f"`{primary_fname}`"
                cls._ensure_field(qfields, primary_fname, fallback_expr)
            if len(y_fields) > 1:
                secondary_fname = y_fields[1].get("field") or y_fields[1].get("fieldName") or ""
                if secondary_fname:
                    fallback_expr = f"SUM(`{secondary_fname}`)" if not query_fields else f"`{secondary_fname}`"
                    cls._ensure_field(qfields, secondary_fname, fallback_expr)

        y_encoding: Dict[str, Any] = {
            "fieldName": primary_fname,
            "displayName": _clean_title(primary_fname),
            "scale": {"type": "quantitative"},
        }
        if secondary_fname:
            y_encoding["secondary"] = {
                "fields": [{"fieldName": secondary_fname}],
                "scale": {"type": "quantitative"},
            }

        encodings: Dict[str, Any] = {
            "x": _axis_encoding(x_field, infer_scale_type(x_field)),
            "y": y_encoding,
            "color": {"legend": {}},
            "label": {"show": True},
        }

        spec: Dict[str, Any] = {
            "version": 1,
            "widgetType": "combo",
            "frame": _frame(title, show_title, fallback=_clean_title(x_field)),
            "encodings": encodings,
            "data": {"queryName": "main_query"},
        }

        ok, errs = validate_widget_spec(spec)
        if not ok:
            raise ValueError(f"Invalid combo widget spec: {errs}")

        return Widget(
            queries=[cls._create_widget_query(dataset_name, qfields, False)],
            spec=spec,
        )
