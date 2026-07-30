"""
lakeview_generator.py — Lakeview AST Generator (Rewritten)
============================================================
Converts Universal BI Model (UBIM) to Databricks Lakeview AST model.

Fixes applied:
  - Widget query `fields`: populates exact `[{"expression": "...", "name": "..."}]` matching query fields
  - Widget query `disaggregated`: set correctly (False for charts/counters, True for tables)
  - Color marks: adds standard Lakeview color palette `mark.colors`
  - Pie chart encodings: uses `x` (category) and `y` (value), matching Lakeview schema
  - Complete spec encodings: adds `displayName`, `scale`, and `axis` titles
  - Chart types supported: BAR, LINE, AREA, SCATTER, PIE, COUNTER, TABLE, FILTER
"""

import re
from typing import Dict, Any, List
from app.models.universal_model import IntermediateDashboard, ChartType, EncodingChannel
from app.models.lakeview_model import (
    LakeviewDashboard, Dataset, Page, Widget, Position, LayoutItem,
    WidgetQuery, generate_lakeview_id
)
from app.services.generator.layout_engine import project_to_6column_grid

# Standard Databricks palette
DEFAULT_COLORS = [
    "#077A9D", "#FFAB00", "#00A972", "#FF3621",
    "#8BCAE7", "#AB4057", "#99DDB4", "#FCA4A1",
    "#919191", "#BF7080"
]

# P0.3: Placeholder field names that indicate unresolved data binding
PLACEHOLDER_FIELDS = {'x', 'y', 'value', 'filter_col', 'X', 'Y', 'Value', '0', ''}

# P1.3: Minimum query fields required per chart type
MIN_FIELDS_FOR_CHART = {
    ChartType.BAR: 1,
    ChartType.LINE: 1,
    ChartType.AREA: 1,
    ChartType.SCATTER: 2,
    ChartType.PIE: 2,
    ChartType.COUNTER: 1,
    ChartType.TABLE: 1,
    ChartType.FILTER_MULTI: 1,
    ChartType.FILTER_SINGLE: 1,
    ChartType.FILTER_DATE: 1,
}


def generate_lakeview_dashboard(ubim: IntermediateDashboard) -> LakeviewDashboard:
    """Stage 8 Lakeview Generator: Converts Universal BI Model (UBIM) to Databricks Lakeview AST model."""
    lakeview = LakeviewDashboard(datasets=[], pages=[])

    # 1. Map Datasets
    ds_id_map = {}
    for ubim_ds in ubim.datasets:
        dataset_id = generate_lakeview_id()
        ds_id_map[ubim_ds.name] = dataset_id
        lakeview.datasets.append(Dataset(
            name=dataset_id,
            displayName=ubim_ds.name,
            query=ubim_ds.sql_query
        ))

    # 2. Map Pages and Layout Items
    for ubim_page in ubim.pages:
        page = Page(name=generate_lakeview_id(), displayName=ubim_page.name, layout=[])
        projected_widgets = project_to_6column_grid(ubim_page.widgets)

        for w_ubim in projected_widgets:
            dataset_ref = ds_id_map.get(
                w_ubim.dataset_name,
                lakeview.datasets[0].name if lakeview.datasets else "default_ds"
            )
            pos = Position(
                x=w_ubim.position.grid_x,
                y=w_ubim.position.grid_y,
                width=w_ubim.position.grid_w,
                height=w_ubim.position.grid_h
            )

            # Build Query Fields & Widget Query (P0.1 Critical Fix)
            query_fields_list = []
            if w_ubim.query_fields:
                for qf in w_ubim.query_fields:
                    query_fields_list.append({
                        "expression": qf.expression,
                        "name": qf.name
                    })
            elif w_ubim.encodings:
                # Fallback from encodings if query_fields missing
                for enc in w_ubim.encodings:
                    expr = enc.expression_sql or f"`{enc.field_name}`"
                    query_fields_list.append({
                        "expression": expr,
                        "name": enc.field_name
                    })

            # Do NOT invent query fields by scraping dataset SQL column order.
            # That fabricates unrelated bindings (e.g. first two columns as pie x/y).
            # Tables may still list encoding-derived fields above; charts must have
            # real UBIM query_fields/encodings or they are skipped below.

            is_disaggregated = w_ubim.disaggregated

            widget_query = WidgetQuery(
                name="main_query",
                query={
                    "datasetName": dataset_ref,
                    "disaggregated": is_disaggregated,
                    "fields": query_fields_list
                }
            )

            # Build Widget Specs (P1.1 High Fix)
            spec: Dict[str, Any] = {}
            title = w_ubim.title or w_ubim.name

            # Helper for channel fields — only from real UBIM encodings / query fields
            x_enc = next((e for e in w_ubim.encodings if e.channel == EncodingChannel.X), None)
            y_enc = next((e for e in w_ubim.encodings if e.channel == EncodingChannel.Y), None)
            color_enc = next((e for e in w_ubim.encodings if e.channel == EncodingChannel.COLOR), None)

            x_field = None
            if x_enc:
                x_field = x_enc.field_name
            elif color_enc and w_ubim.chart_type == ChartType.PIE:
                x_field = color_enc.field_name
            elif query_fields_list and w_ubim.chart_type == ChartType.TABLE:
                x_field = query_fields_list[0]["name"]

            y_field = None
            if y_enc:
                y_field = y_enc.field_name
            elif query_fields_list and w_ubim.chart_type == ChartType.TABLE:
                other_fields = [qf["name"] for qf in query_fields_list if qf["name"] != x_field]
                y_field = other_fields[0] if other_fields else x_field

            # Chart widgets without explicit X/Y from UBIM encodings are incomplete —
            # do not invent from SQL column order.
            if w_ubim.chart_type in (
                ChartType.BAR, ChartType.LINE, ChartType.AREA, ChartType.SCATTER, ChartType.PIE
            ):
                if x_field is None and query_fields_list:
                    # Prefer first non-aggregated / categorical-looking field from encodings
                    dim_enc = next(
                        (e for e in w_ubim.encodings if e.channel in (EncodingChannel.COLOR, EncodingChannel.X)),
                        None,
                    )
                    if dim_enc:
                        x_field = dim_enc.field_name
                    elif len(query_fields_list) >= 1 and y_enc:
                        x_field = query_fields_list[0]["name"]
                if y_field is None:
                    measure_enc = next(
                        (e for e in w_ubim.encodings if e.channel in (EncodingChannel.Y, EncodingChannel.SIZE)),
                        None,
                    )
                    if measure_enc:
                        y_field = measure_enc.field_name

            # Defaults only for incomplete detection — never invent real column names
            if x_field is None:
                x_field = "x"
            if y_field is None:
                y_field = "y"

            # ── P0.3: Skip widgets with empty fields or placeholder encodings ──
            has_real_fields = len(query_fields_list) > 0
            has_placeholder_x = x_field in PLACEHOLDER_FIELDS
            has_placeholder_y = y_field in PLACEHOLDER_FIELDS
            incomplete_sql = False
            if lakeview.datasets:
                ds_match = next((d for d in lakeview.datasets if d.name == dataset_ref), None)
                if ds_match and ds_match.query and "__incomplete_projection__" in ds_match.query:
                    incomplete_sql = True

            # If no real query fields exist, skip the widget entirely
            if not has_real_fields or incomplete_sql:
                import logging
                logging.warning(
                    f"Skipping widget '{w_ubim.title or w_ubim.name}' — "
                    f"{'incomplete SQL projection' if incomplete_sql else 'no query fields resolved'}. "
                    f"Original chart_type={w_ubim.chart_type.value}"
                )
                continue

            # If all encoding field names are placeholders, skip the widget
            if has_placeholder_x and has_placeholder_y:
                import logging
                logging.warning(
                    f"Skipping widget '{w_ubim.title or w_ubim.name}' — placeholder encodings "
                    f"(x='{x_field}', y='{y_field}'). chart_type={w_ubim.chart_type.value}"
                )
                continue

            # Charts that require category+measure must have both from UBIM (not invented)
            if w_ubim.chart_type == ChartType.PIE and (has_placeholder_x or has_placeholder_y):
                import logging
                logging.warning(
                    f"Skipping pie widget '{w_ubim.title or w_ubim.name}' — missing categorical "
                    f"or quantitative binding (x='{x_field}', y='{y_field}')"
                )
                continue

            # Scatter requires 2 distinct quantitative fields
            if w_ubim.chart_type == ChartType.SCATTER and x_field == y_field:
                import logging
                logging.warning(
                    f"Demoting widget '{w_ubim.title or w_ubim.name}' from scatter to bar — "
                    f"x and y reference the same field '{x_field}'"
                )
                w_ubim.chart_type = ChartType.BAR

            # Counter requires at least one real value field
            if w_ubim.chart_type == ChartType.COUNTER:
                val_field_candidate = query_fields_list[0]["name"] if query_fields_list else "value"
                if val_field_candidate in PLACEHOLDER_FIELDS:
                    import logging
                    logging.warning(
                        f"Skipping counter widget '{w_ubim.title or w_ubim.name}' — "
                        f"no valid value field"
                    )
                    continue

            if w_ubim.chart_type == ChartType.BAR:
                encodings_cfg: Dict[str, Any] = {
                    "x": {
                        "fieldName": x_field,
                        "displayName": x_field.replace('_', ' ').title(),
                        "scale": {"type": "categorical"},
                        "axis": {"title": x_field.replace('_', ' ').title()}
                    },
                    "y": {
                        "fieldName": y_field,
                        "displayName": y_field.replace('_', ' ').title(),
                        "scale": {"type": "quantitative"},
                        "axis": {"title": y_field.replace('_', ' ').title()}
                    },
                    "label": {"show": False}
                }
                if color_enc:
                    encodings_cfg["color"] = {
                        "fieldName": color_enc.field_name,
                        "displayName": color_enc.field_name.replace('_', ' ').title(),
                        "scale": {"type": "categorical"}
                    }
                spec = {
                    "version": 3,
                    "widgetType": "bar",
                    "encodings": encodings_cfg,
                    "frame": {"title": title, "showTitle": True},
                    "mark": {"colors": DEFAULT_COLORS}
                }

            elif w_ubim.chart_type in (ChartType.LINE, ChartType.AREA):
                widget_kind = "line" if w_ubim.chart_type == ChartType.LINE else "area"
                encodings_cfg = {
                    "x": {
                        "fieldName": x_field,
                        "displayName": x_field.replace('_', ' ').title(),
                        "scale": {"type": "temporal"},
                        "axis": {"title": x_field.replace('_', ' ').title()}
                    },
                    "y": {
                        "fieldName": y_field,
                        "displayName": y_field.replace('_', ' ').title(),
                        "scale": {"type": "quantitative"},
                        "axis": {"title": y_field.replace('_', ' ').title()}
                    },
                    "label": {"show": False}
                }
                if color_enc:
                    encodings_cfg["color"] = {
                        "fieldName": color_enc.field_name,
                        "displayName": color_enc.field_name.replace('_', ' ').title(),
                        "scale": {"type": "categorical"}
                    }
                spec = {
                    "version": 3,
                    "widgetType": widget_kind,
                    "encodings": encodings_cfg,
                    "frame": {"title": title, "showTitle": True},
                    "mark": {"colors": DEFAULT_COLORS}
                }

            elif w_ubim.chart_type == ChartType.SCATTER:
                spec = {
                    "version": 3,
                    "widgetType": "scatter",
                    "encodings": {
                        "x": {
                            "fieldName": x_field,
                            "displayName": x_field.replace('_', ' ').title(),
                            "scale": {"type": "quantitative"},
                            "axis": {"title": x_field.replace('_', ' ').title()}
                        },
                        "y": {
                            "fieldName": y_field,
                            "displayName": y_field.replace('_', ' ').title(),
                            "scale": {"type": "quantitative"},
                            "axis": {"title": y_field.replace('_', ' ').title()}
                        }
                    },
                    "frame": {"title": title, "showTitle": True},
                    "mark": {"colors": DEFAULT_COLORS}
                }

            elif w_ubim.chart_type == ChartType.PIE:
                spec = {
                    "version": 3,
                    "widgetType": "pie",
                    "encodings": {
                        "x": {
                            "fieldName": x_field,
                            "displayName": x_field.replace('_', ' ').title(),
                            "scale": {"type": "categorical"}
                        },
                        "y": {
                            "fieldName": y_field,
                            "displayName": y_field.replace('_', ' ').title(),
                            "scale": {"type": "quantitative"}
                        }
                    },
                    "frame": {"title": title, "showTitle": True},
                    "mark": {"colors": DEFAULT_COLORS}
                }

            elif w_ubim.chart_type == ChartType.COUNTER:
                val_field = query_fields_list[0]["name"] if query_fields_list else "value"
                spec = {
                    "version": 2,
                    "widgetType": "counter",
                    "encodings": {
                        "value": {
                            "fieldName": val_field,
                            "displayName": title
                        }
                    },
                    "frame": {"title": title, "showTitle": True}
                }

            elif w_ubim.chart_type in (ChartType.FILTER_MULTI, ChartType.FILTER_SINGLE, ChartType.FILTER_DATE):
                filt_type = "filter-multi-select"
                if w_ubim.chart_type == ChartType.FILTER_SINGLE:
                    filt_type = "filter-single-select"
                elif w_ubim.chart_type == ChartType.FILTER_DATE:
                    filt_type = "filter-date-range-picker"
                
                f_field = query_fields_list[0]["name"] if query_fields_list else "filter_col"
                # P0.3: Skip filter widgets with placeholder fields
                if f_field in PLACEHOLDER_FIELDS:
                    import logging
                    logging.warning(
                        f"Skipping filter widget '{w_ubim.title or w_ubim.name}' — "
                        f"no valid filter field resolved"
                    )
                    continue
                spec = {
                    "version": 2,
                    "widgetType": filt_type,
                    "encodings": {
                        "fields": [
                            {
                                "fieldName": f_field,
                                "displayName": f_field.replace('_', ' ').title(),
                                "queryName": f"dashboards/{generate_lakeview_id()}/datasets/{dataset_ref}_{f_field}"
                            }
                        ]
                    },
                    "frame": {"title": title, "showTitle": True}
                }

            elif w_ubim.chart_type == ChartType.HEATMAP:
                spec = {
                    "version": 3,
                    "widgetType": "bar",
                    "encodings": {
                        "x": {
                            "fieldName": x_field,
                            "displayName": x_field.replace('_', ' ').title(),
                            "scale": {"type": "categorical"},
                            "axis": {"title": x_field.replace('_', ' ').title()}
                        },
                        "y": {
                            "fieldName": y_field,
                            "displayName": y_field.replace('_', ' ').title(),
                            "scale": {"type": "quantitative"},
                            "axis": {"title": y_field.replace('_', ' ').title()}
                        },
                        "label": {"show": False}
                    },
                    "frame": {"title": title, "showTitle": True},
                    "mark": {"colors": DEFAULT_COLORS}
                }

            elif w_ubim.chart_type == ChartType.HISTOGRAM:
                spec = {
                    "version": 3,
                    "widgetType": "bar",
                    "encodings": {
                        "x": {
                            "fieldName": x_field,
                            "displayName": x_field.replace('_', ' ').title(),
                            "scale": {"type": "categorical"},
                            "axis": {"title": x_field.replace('_', ' ').title()}
                        },
                        "y": {
                            "fieldName": y_field,
                            "displayName": y_field.replace('_', ' ').title(),
                            "scale": {"type": "quantitative"},
                            "axis": {"title": y_field.replace('_', ' ').title()}
                        },
                        "label": {"show": False}
                    },
                    "frame": {"title": title, "showTitle": True},
                    "mark": {"colors": DEFAULT_COLORS}
                }

            elif w_ubim.chart_type in (ChartType.MAP, ChartType.BOXPLOT, ChartType.COMBO):
                # MAP/BOXPLOT/COMBO: Lakeview doesn't support these natively — degrade to table
                cols_list = []
                for idx, qf in enumerate(query_fields_list):
                    col_name = qf["name"]
                    cols_list.append({
                        "fieldName": col_name,
                        "displayName": col_name.replace('_', ' ').title(),
                        "title": col_name.replace('_', ' ').title(),
                        "type": "string",
                        "displayAs": "string",
                        "alignContent": "left",
                        "visible": True,
                        "order": 100000 + idx
                    })
                spec = {
                    "version": 1,
                    "widgetType": "table",
                    "encodings": {"columns": cols_list},
                    "frame": {"title": f"{title} (converted from {w_ubim.chart_type.value})", "showTitle": True},
                    "condensed": True,
                    "itemsPerPage": 25
                }

            else:
                # Table Spec (Version 1) — default fallback
                cols_list = []
                for idx, qf in enumerate(query_fields_list):
                    col_name = qf["name"]
                    cols_list.append({
                        "fieldName": col_name,
                        "displayName": col_name.replace('_', ' ').title(),
                        "title": col_name.replace('_', ' ').title(),
                        "type": "string",
                        "displayAs": "string",
                        "alignContent": "left",
                        "visible": True,
                        "order": 100000 + idx
                    })
                spec = {
                    "version": 1,
                    "widgetType": "table",
                    "encodings": {"columns": cols_list},
                    "frame": {"title": title, "showTitle": True},
                    "condensed": True,
                    "itemsPerPage": 25
                }

            widget = Widget(
                name=generate_lakeview_id(),
                queries=[widget_query],
                spec=spec,
            )

            layout_item = LayoutItem(widget=widget, position=pos)
            page.layout.append(layout_item)

        lakeview.pages.append(page)

    return lakeview
