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

            if not query_fields_list and lakeview.datasets:
                ds_match = next((d for d in lakeview.datasets if d.name == dataset_ref), None)
                if ds_match and ds_match.query:
                    cols_in_query = re.findall(r'`([^`]+)`', ds_match.query)
                    if cols_in_query:
                        for c_name in cols_in_query[:20]:
                            query_fields_list.append({
                                "expression": f"`{c_name}`",
                                "name": c_name
                            })

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

            # Helper for channel fields
            x_enc = next((e for e in w_ubim.encodings if e.channel == EncodingChannel.X), None)
            y_enc = next((e for e in w_ubim.encodings if e.channel == EncodingChannel.Y), None)
            color_enc = next((e for e in w_ubim.encodings if e.channel == EncodingChannel.COLOR), None)

            x_field = x_enc.field_name if x_enc else (query_fields_list[0]["name"] if query_fields_list else "x")
            if y_enc:
                y_field = y_enc.field_name
            else:
                other_fields = [qf["name"] for qf in query_fields_list if qf["name"] != x_field]
                if other_fields:
                    y_field = other_fields[0]
                elif query_fields_list:
                    y_field = query_fields_list[0]["name"]
                else:
                    y_field = x_field

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
