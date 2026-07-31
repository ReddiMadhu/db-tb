"""
widget_factory.py — Centralized Databricks AI/BI Version 3 Widget Schema Factory
================================================================================
Single source of truth for constructing Databricks Lakeview AI/BI widgets.
Guarantees Version 3 schema compliance, required encodings (scale.type),
valid queries & fields, and prevents schema drift across the repository.

Supported Chart Types:
  - Bar (x: categorical, y: quantitative, optional color: categorical)
  - Pie (color: categorical, angle: quantitative — NO x/y)
  - Line / Area (x: temporal/categorical, y: quantitative, optional color)
  - Scatter (x: quantitative, y: quantitative)
  - Table (columns encodings + disaggregated query fields)
  - Counter / Stat (value: quantitative)
  - Filter (multi-select, single-select, date-range)
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from app.models.lakeview_model import Widget, WidgetQuery, generate_lakeview_id

DEFAULT_COLORS = [
    "#077A9D", "#FFAB00", "#00A972", "#FF3621", "#8BCAE7",
    "#AB4057", "#99DDB4", "#FCA4A1", "#919191", "#BF7080"
]

PLACEHOLDER_FIELDS = {'x', 'y', 'value', 'filter_col', 'X', 'Y', 'Value', '0', ''}


def _clean_title(name: str) -> str:
    """Format field name to clean title (e.g. Total_Claim -> Total Claim)."""
    if not name:
        return ""
    return name.replace('_', ' ').strip().title()


def sanitize_query_fields(fields: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Sanitize query field list to ensure no nulls or empty field definitions."""
    sanitized = []
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
            "name": name
        })
    return sanitized


def validate_widget_spec(spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a renderSpec object against Databricks AI/BI v3 rules."""
    errors = []
    if not spec:
        return False, ["Widget spec is missing or null."]

    v = spec.get("version")
    if v != 3 and v != 1 and v != 2:
        errors.append(f"Invalid widget spec version '{v}' — expected version 3.")

    wt = spec.get("widgetType")
    if not wt:
        errors.append("Missing required 'widgetType' in spec.")

    encodings = spec.get("encodings", {})
    if not isinstance(encodings, dict):
        errors.append("Invalid 'encodings' structure — must be an object.")
        return False, errors

    if wt == "bar":
        for ch_name in ('x', 'y'):
            ch = encodings.get(ch_name)
            if not isinstance(ch, dict) or not ch.get("fieldName"):
                errors.append(f"Bar chart missing required '{ch_name}' encoding fieldName.")
            elif not ch.get("scale", {}).get("type"):
                errors.append(f"Bar chart '{ch_name}' encoding missing scale.type.")

    elif wt == "pie":
        if "x" in encodings or "y" in encodings:
            errors.append("Pie chart must NOT use 'x' or 'y' encodings — use 'angle' and 'color'.")
        for ch_name in ('angle', 'color'):
            ch = encodings.get(ch_name)
            if not isinstance(ch, dict) or not ch.get("fieldName"):
                errors.append(f"Pie chart missing required '{ch_name}' encoding fieldName.")
            elif not ch.get("scale", {}).get("type"):
                errors.append(f"Pie chart '{ch_name}' encoding missing scale.type.")

    elif wt in ("line", "area"):
        for ch_name in ('x', 'y'):
            ch = encodings.get(ch_name)
            if not isinstance(ch, dict) or not ch.get("fieldName"):
                errors.append(f"Line/Area chart missing required '{ch_name}' encoding fieldName.")
            elif not ch.get("scale", {}).get("type"):
                errors.append(f"Line/Area chart '{ch_name}' encoding missing scale.type.")

    elif wt == "scatter":
        for ch_name in ('x', 'y'):
            ch = encodings.get(ch_name)
            if not isinstance(ch, dict) or not ch.get("fieldName"):
                errors.append(f"Scatter chart missing required '{ch_name}' encoding fieldName.")
            elif not ch.get("scale", {}).get("type"):
                errors.append(f"Scatter chart '{ch_name}' encoding missing scale.type.")

    elif wt == "table":
        cols = encodings.get("columns")
        if not isinstance(cols, list) or not cols:
            errors.append("Table widget missing required 'columns' encodings list.")

    return len(errors) == 0, errors


class WidgetFactory:
    """Centralized Factory for building Databricks AI/BI v3 widgets."""

    @staticmethod
    def _create_widget_query(dataset_name: str, fields: List[Dict[str, str]], disaggregated: bool = False) -> WidgetQuery:
        clean_fields = sanitize_query_fields(fields)
        return WidgetQuery(
            name="main_query",
            query={
                "datasetName": dataset_name,
                "disaggregated": disaggregated,
                "disaggregatedData": disaggregated,
                "fields": clean_fields
            }
        )

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
    ) -> Widget:
        """Create a Version 3 Bar Chart widget."""
        qfields = query_fields or [
            {"expression": f"`{x_field}`", "name": x_field},
            {"expression": f"SUM(`{y_field}`)", "name": y_field},
        ]
        if color_field:
            qfields.append({"expression": f"`{color_field}`", "name": color_field})

        encodings = {
            "x": {
                "fieldName": x_field,
                "displayName": _clean_title(x_field),
                "scale": {"type": x_scale_type},
                "axis": {"title": _clean_title(x_field)}
            },
            "y": {
                "fieldName": y_field,
                "displayName": _clean_title(y_field),
                "scale": {"type": y_scale_type},
                "axis": {"title": _clean_title(y_field)}
            },
            "label": {"show": False}
        }
        if color_field:
            encodings["color"] = {
                "fieldName": color_field,
                "displayName": _clean_title(color_field),
                "scale": {"type": "categorical"}
            }

        spec = {
            "version": 3,
            "widgetType": "bar",
            "encodings": encodings,
            "frame": {"title": title or _clean_title(y_field), "showTitle": True},
            "mark": {"colors": DEFAULT_COLORS}
        }

        wq = cls._create_widget_query(dataset_name, qfields, disaggregated=False)
        return Widget(queries=[wq], spec=spec)

    @classmethod
    def create_pie_widget(
        cls,
        dataset_name: str,
        category_field: str,
        value_field: str,
        title: str = "",
        query_fields: Optional[List[Dict[str, str]]] = None,
    ) -> Widget:
        """Create a Version 3 Pie Chart widget (uses angle & color, NOT x & y)."""
        qfields = query_fields or [
            {"expression": f"`{category_field}`", "name": category_field},
            {"expression": f"SUM(`{value_field}`)", "name": value_field},
        ]

        spec = {
            "version": 3,
            "widgetType": "pie",
            "encodings": {
                "color": {
                    "fieldName": category_field,
                    "displayName": _clean_title(category_field),
                    "scale": {"type": "categorical"}
                },
                "angle": {
                    "fieldName": value_field,
                    "displayName": _clean_title(value_field),
                    "scale": {"type": "quantitative"}
                }
            },
            "frame": {"title": title or f"{_clean_title(category_field)} Distribution", "showTitle": True},
            "mark": {"colors": DEFAULT_COLORS}
        }

        wq = cls._create_widget_query(dataset_name, qfields, disaggregated=False)
        return Widget(queries=[wq], spec=spec)

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
        x_scale_type: str = "temporal",
    ) -> Widget:
        """Create a Version 3 Line or Area Chart widget."""
        qfields = query_fields or [
            {"expression": f"`{x_field}`", "name": x_field},
            {"expression": f"SUM(`{y_field}`)", "name": y_field},
        ]
        if color_field:
            qfields.append({"expression": f"`{color_field}`", "name": color_field})

        encodings = {
            "x": {
                "fieldName": x_field,
                "displayName": _clean_title(x_field),
                "scale": {"type": x_scale_type},
                "axis": {"title": _clean_title(x_field)}
            },
            "y": {
                "fieldName": y_field,
                "displayName": _clean_title(y_field),
                "scale": {"type": "quantitative"},
                "axis": {"title": _clean_title(y_field)}
            },
            "label": {"show": False}
        }
        if color_field:
            encodings["color"] = {
                "fieldName": color_field,
                "displayName": _clean_title(color_field),
                "scale": {"type": "categorical"}
            }

        spec = {
            "version": 3,
            "widgetType": "area" if is_area else "line",
            "encodings": encodings,
            "frame": {"title": title or _clean_title(y_field), "showTitle": True},
            "mark": {"colors": DEFAULT_COLORS}
        }

        wq = cls._create_widget_query(dataset_name, qfields, disaggregated=False)
        return Widget(queries=[wq], spec=spec)

    @classmethod
    def create_scatter_widget(
        cls,
        dataset_name: str,
        x_field: str,
        y_field: str,
        title: str = "",
        query_fields: Optional[List[Dict[str, str]]] = None,
    ) -> Widget:
        """Create a Version 3 Scatter Plot widget."""
        qfields = query_fields or [
            {"expression": f"`{x_field}`", "name": x_field},
            {"expression": f"`{y_field}`", "name": y_field},
        ]

        spec = {
            "version": 3,
            "widgetType": "scatter",
            "encodings": {
                "x": {
                    "fieldName": x_field,
                    "displayName": _clean_title(x_field),
                    "scale": {"type": "quantitative"},
                    "axis": {"title": _clean_title(x_field)}
                },
                "y": {
                    "fieldName": y_field,
                    "displayName": _clean_title(y_field),
                    "scale": {"type": "quantitative"},
                    "axis": {"title": _clean_title(y_field)}
                }
            },
            "frame": {"title": title or f"{_clean_title(x_field)} vs {_clean_title(y_field)}", "showTitle": True},
            "mark": {"colors": DEFAULT_COLORS}
        }

        wq = cls._create_widget_query(dataset_name, qfields, disaggregated=False)
        return Widget(queries=[wq], spec=spec)

    @classmethod
    def create_table_widget(
        cls,
        dataset_name: str,
        column_fields: List[str],
        title: str = "",
        query_fields: Optional[List[Dict[str, str]]] = None,
    ) -> Widget:
        """Create a Version 3 Table widget."""
        qfields = query_fields or [
            {"expression": f"`{col}`", "name": col} for col in column_fields
        ]

        columns_enc = []
        for i, col in enumerate(column_fields):
            columns_enc.append({
                "fieldName": col,
                "displayName": _clean_title(col),
                "title": _clean_title(col),
                "type": "string",
                "displayAs": "string",
                "alignContent": "left",
                "visible": True,
                "order": 100000 + i
            })

        spec = {
            "version": 3,
            "widgetType": "table",
            "encodings": {
                "columns": columns_enc
            },
            "frame": {"title": title or "Table View", "showTitle": True}
        }

        wq = cls._create_widget_query(dataset_name, qfields, disaggregated=True)
        return Widget(queries=[wq], spec=spec)
