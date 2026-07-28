#!/usr/bin/env python3
"""
Databricks Lakeview (AI/BI) Dashboard Creator — Production-Grade Script
=======================================================================
Creates, publishes, and manages Databricks AI/BI dashboards entirely from code.

This script demonstrates every operation needed for a migration engine:
  1. Building serialized_dashboard JSON from scratch
  2. Creating dashboards via the REST API / Python SDK
  3. Publishing with credential embedding
  4. Updating, cloning, scheduling, and managing lifecycle

Requirements:
  pip install databricks-sdk requests

Usage:
  # Using Databricks SDK (recommended):
  export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
  export DATABRICKS_TOKEN=dapi...
  python create_lakeview_dashboard.py --warehouse-id <sql_warehouse_id>

  # Or using raw REST API:
  python create_lakeview_dashboard.py --mode rest --host https://... --token dapi... --warehouse-id ...

Author: Reverse-engineered from Databricks bundle-examples, SDK source, and Terraform provider.
Evidence Level: Schema structures are [Verified] from NYC Taxi example (SHA: 07d8a5815e12b4480a75358d1d0ab0f8a09bc41e).
"""

import argparse
import json
import os
import sys
import uuid
import requests
from typing import Any, Dict, List, Optional


# =============================================================================
# SECTION 1: Dashboard Object Model (Verified Schema)
# =============================================================================

def generate_hex_id() -> str:
    """Generate an 8-character hex ID matching Databricks naming convention. [Verified]"""
    return uuid.uuid4().hex[:8]


class Field:
    """A field expression within a widget query. [Verified]"""

    def __init__(self, expression: str, name: str):
        self.expression = expression
        self.name = name

    def to_dict(self) -> dict:
        return {"expression": self.expression, "name": self.name}


class QueryDefinition:
    """Defines how a widget binds to a dataset. [Verified]"""

    def __init__(self, dataset_name: str, fields: List[Field], disaggregated: bool = False):
        self.dataset_name = dataset_name
        self.fields = fields
        self.disaggregated = disaggregated

    def to_dict(self) -> dict:
        return {
            "datasetName": self.dataset_name,
            "disaggregated": self.disaggregated,
            "fields": [f.to_dict() for f in self.fields],
        }


class WidgetQuery:
    """A named query binding for a widget. [Verified]"""

    def __init__(self, name: str, query: QueryDefinition):
        self.name = name
        self.query = query

    def to_dict(self) -> dict:
        return {"name": self.name, "query": self.query.to_dict()}


class Position:
    """Grid position on the 6-column layout. [Verified]
    
    Grid Rules:
      - x: column start (0-5)
      - y: row start (0+, increases downward)
      - width: columns spanned (1-6, x + width <= 6)
      - height: rows spanned (1+)
    """

    def __init__(self, x: int, y: int, width: int, height: int):
        assert 0 <= x <= 5, f"x must be 0-5, got {x}"
        assert x + width <= 6, f"x + width must be <= 6, got {x + width}"
        assert width >= 1, f"width must be >= 1, got {width}"
        assert height >= 1, f"height must be >= 1, got {height}"
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


# --- Encoding helpers ---

class AxisEncoding:
    """Axis encoding for x/y channels. [Verified]"""

    def __init__(self, field_name: str, display_name: str,
                 scale_type: str = "quantitative", axis_title: Optional[str] = None):
        self.field_name = field_name
        self.display_name = display_name
        self.scale_type = scale_type  # quantitative | temporal | categorical | ordinal
        self.axis_title = axis_title

    def to_dict(self) -> dict:
        result: dict = {
            "fieldName": self.field_name,
            "displayName": self.display_name,
            "scale": {"type": self.scale_type},
        }
        if self.axis_title:
            result["axis"] = {"title": self.axis_title}
        return result


class ColorEncoding:
    """Color channel encoding for grouping. [Verified]"""

    def __init__(self, field_name: str, display_name: str, scale_type: str = "categorical"):
        self.field_name = field_name
        self.display_name = display_name
        self.scale_type = scale_type

    def to_dict(self) -> dict:
        return {
            "fieldName": self.field_name,
            "displayName": self.display_name,
            "scale": {"type": self.scale_type},
        }


class TableColumn:
    """Table column definition with full formatting. [Verified from NYC Taxi]"""

    def __init__(self, field_name: str, display_name: str, title: str,
                 col_type: str = "string", display_as: str = "string",
                 align: str = "left", visible: bool = True, order: int = 100000,
                 number_format: Optional[str] = None,
                 cell_format: Optional[dict] = None):
        self.field_name = field_name
        self.display_name = display_name
        self.title = title
        self.col_type = col_type
        self.display_as = display_as
        self.align = align
        self.visible = visible
        self.order = order
        self.number_format = number_format
        self.cell_format = cell_format

    def to_dict(self) -> dict:
        result = {
            "fieldName": self.field_name,
            "displayName": self.display_name,
            "title": self.title,
            "type": self.col_type,
            "displayAs": self.display_as,
            "alignContent": self.align,
            "visible": self.visible,
            "order": self.order,
            "allowHTML": False,
            "allowSearch": False,
            "booleanValues": ["false", "true"],
            "highlightLinks": False,
            "imageHeight": "",
            "imageTitleTemplate": "{{ @ }}",
            "imageUrlTemplate": "{{ @ }}",
            "imageWidth": "",
            "linkOpenInNewTab": True,
            "linkTextTemplate": "{{ @ }}",
            "linkTitleTemplate": "{{ @ }}",
            "linkUrlTemplate": "{{ @ }}",
            "preserveWhitespace": False,
            "useMonospaceFont": False,
        }
        if self.number_format:
            result["numberFormat"] = self.number_format
        if self.cell_format:
            result["cellFormat"] = self.cell_format
        return result


# --- Widget Spec Builders ---

class WidgetSpec:
    """Base widget spec. [Verified]"""

    def __init__(self, widget_type: str, version: int, title: str, show_title: bool = True):
        self.widget_type = widget_type
        self.version = version
        self.title = title
        self.show_title = show_title

    def _base_dict(self) -> dict:
        return {
            "version": self.version,
            "widgetType": self.widget_type,
            "frame": {"showTitle": self.show_title, "title": self.title},
        }


class CounterSpec(WidgetSpec):
    """Counter/KPI widget. [Verified: version=2, widgetType='counter']"""

    DEFAULT_COLORS = ["#077A9D", "#FFAB00", "#00A972", "#FF3621",
                      "#8BCAE7", "#AB4057", "#99DDB4", "#FCA4A1",
                      "#919191", "#BF7080"]

    def __init__(self, title: str, value_field: str, value_display: str):
        super().__init__("counter", 2, title)
        self.value_field = value_field
        self.value_display = value_display

    def to_dict(self) -> dict:
        d = self._base_dict()
        d["encodings"] = {
            "value": {"fieldName": self.value_field, "displayName": self.value_display}
        }
        return d


class BarChartSpec(WidgetSpec):
    """Bar chart widget. [Verified: version=3, widgetType='bar']"""

    DEFAULT_COLORS = ["#077A9D", "#FFAB00", "#00A972", "#FF3621",
                      "#8BCAE7", "#AB4057", "#99DDB4", "#FCA4A1",
                      "#919191", "#BF7080"]

    def __init__(self, title: str, x: AxisEncoding, y: AxisEncoding,
                 color: Optional[ColorEncoding] = None,
                 colors: Optional[List[str]] = None,
                 show_labels: bool = False):
        super().__init__("bar", 3, title)
        self.x = x
        self.y = y
        self.color = color
        self.colors = colors or self.DEFAULT_COLORS
        self.show_labels = show_labels

    def to_dict(self) -> dict:
        d = self._base_dict()
        encodings: dict = {
            "x": self.x.to_dict(),
            "y": self.y.to_dict(),
            "label": {"show": self.show_labels},
        }
        if self.color:
            encodings["color"] = self.color.to_dict()
        d["encodings"] = encodings
        d["mark"] = {"colors": self.colors}
        return d


class LineChartSpec(WidgetSpec):
    """Line chart widget. [Inferred: same structure as bar, widgetType='line']"""

    DEFAULT_COLORS = ["#077A9D", "#FFAB00", "#00A972", "#FF3621",
                      "#8BCAE7", "#AB4057", "#99DDB4", "#FCA4A1",
                      "#919191", "#BF7080"]

    def __init__(self, title: str, x: AxisEncoding, y: AxisEncoding,
                 color: Optional[ColorEncoding] = None,
                 colors: Optional[List[str]] = None):
        super().__init__("line", 3, title)
        self.x = x
        self.y = y
        self.color = color
        self.colors = colors or self.DEFAULT_COLORS

    def to_dict(self) -> dict:
        d = self._base_dict()
        encodings: dict = {"x": self.x.to_dict(), "y": self.y.to_dict()}
        if self.color:
            encodings["color"] = self.color.to_dict()
        d["encodings"] = encodings
        d["mark"] = {"colors": self.colors}
        return d


class ScatterSpec(WidgetSpec):
    """Scatter plot widget. [Verified: version=3, widgetType='scatter']"""

    DEFAULT_COLORS = ["#077A9D", "#FFAB00", "#00A972", "#FF3621",
                      "#8BCAE7", "#AB4057", "#99DDB4", "#FCA4A1",
                      "#919191", "#BF7080"]

    def __init__(self, title: str, x: AxisEncoding, y: AxisEncoding,
                 color: Optional[ColorEncoding] = None,
                 colors: Optional[List[str]] = None):
        super().__init__("scatter", 3, title)
        self.x = x
        self.y = y
        self.color = color
        self.colors = colors or self.DEFAULT_COLORS

    def to_dict(self) -> dict:
        d = self._base_dict()
        encodings: dict = {"x": self.x.to_dict(), "y": self.y.to_dict()}
        if self.color:
            encodings["color"] = self.color.to_dict()
        d["encodings"] = encodings
        d["mark"] = {"colors": self.colors}
        return d


class PieChartSpec(WidgetSpec):
    """Pie chart widget. [Inferred: version=3, widgetType='pie']"""

    DEFAULT_COLORS = ["#077A9D", "#FFAB00", "#00A972", "#FF3621",
                      "#8BCAE7", "#AB4057", "#99DDB4", "#FCA4A1",
                      "#919191", "#BF7080"]

    def __init__(self, title: str, x: AxisEncoding, y: AxisEncoding,
                 colors: Optional[List[str]] = None):
        super().__init__("pie", 3, title)
        self.x = x
        self.y = y
        self.colors = colors or self.DEFAULT_COLORS

    def to_dict(self) -> dict:
        d = self._base_dict()
        d["encodings"] = {"x": self.x.to_dict(), "y": self.y.to_dict()}
        d["mark"] = {"colors": self.colors}
        return d


class TableSpec(WidgetSpec):
    """Table widget. [Verified: version=1, widgetType='table']"""

    def __init__(self, title: str, columns: List[TableColumn],
                 items_per_page: int = 25, condensed: bool = True,
                 with_row_number: bool = False):
        super().__init__("table", 1, title)
        self.columns = columns
        self.items_per_page = items_per_page
        self.condensed = condensed
        self.with_row_number = with_row_number

    def to_dict(self) -> dict:
        d = self._base_dict()
        d["encodings"] = {"columns": [c.to_dict() for c in self.columns]}
        d["condensed"] = self.condensed
        d["allowHTMLByDefault"] = False
        d["itemsPerPage"] = self.items_per_page
        d["paginationSize"] = "default"
        d["withRowNumber"] = self.with_row_number
        return d


# --- High-Level Builders ---

class Dataset:
    """Dashboard dataset containing a SQL query. [Verified]"""

    def __init__(self, display_name: str, query: str, name: Optional[str] = None):
        self.name = name or generate_hex_id()
        self.display_name = display_name
        self.query = query

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "displayName": self.display_name,
            "query": self.query,
        }


class Widget:
    """A dashboard widget (visualization, text, or filter). [Verified]"""

    def __init__(self, position: Position, spec: Optional[WidgetSpec] = None,
                 queries: Optional[List[WidgetQuery]] = None,
                 textbox_spec: Optional[str] = None,
                 name: Optional[str] = None):
        self.name = name or generate_hex_id()
        self.position = position
        self.spec = spec
        self.queries = queries or []
        self.textbox_spec = textbox_spec

    def to_layout_item(self) -> dict:
        widget_dict: dict = {"name": self.name}
        if self.textbox_spec is not None:
            widget_dict["textbox_spec"] = self.textbox_spec
        else:
            widget_dict["queries"] = [q.to_dict() for q in self.queries]
            if self.spec:
                widget_dict["spec"] = self.spec.to_dict()
        return {
            "position": self.position.to_dict(),
            "widget": widget_dict,
        }


class Page:
    """A dashboard page/tab. [Verified]"""

    def __init__(self, display_name: str, widgets: Optional[List[Widget]] = None,
                 name: Optional[str] = None):
        self.name = name or generate_hex_id()
        self.display_name = display_name
        self.widgets = widgets or []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "displayName": self.display_name,
            "layout": [w.to_layout_item() for w in self.widgets],
        }


class LakeviewDashboard:
    """Complete Lakeview dashboard builder. [Verified]"""

    def __init__(self, datasets: Optional[List[Dataset]] = None,
                 pages: Optional[List[Page]] = None):
        self.datasets = datasets or []
        self.pages = pages or []

    def to_serialized(self) -> str:
        """Generate the serialized_dashboard JSON string."""
        return json.dumps({
            "datasets": [d.to_dict() for d in self.datasets],
            "pages": [p.to_dict() for p in self.pages],
        }, indent=2)

    def save_to_file(self, path: str):
        """Save as .lvdash.json file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_serialized())
        print(f"[OK] Dashboard saved to {path}")


# =============================================================================
# SECTION 2: Helper to Build a Main Query Widget
# =============================================================================

def make_viz_widget(position: Position, dataset: Dataset, spec: WidgetSpec,
                    fields: List[Field], disaggregated: bool = False) -> Widget:
    """Create a visualization widget bound to a dataset. [Verified pattern]"""
    query_def = QueryDefinition(
        dataset_name=dataset.name,
        fields=fields,
        disaggregated=disaggregated,
    )
    widget_query = WidgetQuery(name="main_query", query=query_def)
    return Widget(position=position, spec=spec, queries=[widget_query])


def make_text_widget(position: Position, markdown: str) -> Widget:
    """Create a markdown text widget. [Verified]"""
    return Widget(position=position, textbox_spec=markdown)


# =============================================================================
# SECTION 3: Build a Complete Sample Dashboard
# =============================================================================

def build_sales_dashboard() -> LakeviewDashboard:
    """Build a complete Sales Analytics dashboard from scratch.
    Uses samples.nyctaxi.trips (available on all Databricks workspaces).
    """

    # --- Datasets ---
    ds_trips = Dataset(
        display_name="Trip Summary",
        query=(
            "SELECT\n"
            "  DATE_TRUNC('MONTH', tpep_pickup_datetime) AS month,\n"
            "  pickup_zip,\n"
            "  COUNT(*) AS total_trips,\n"
            "  SUM(fare_amount) AS total_revenue,\n"
            "  AVG(fare_amount) AS avg_fare,\n"
            "  AVG(trip_distance) AS avg_distance\n"
            "FROM `samples`.`nyctaxi`.`trips`\n"
            "WHERE fare_amount > 0 AND fare_amount < 500\n"
            "GROUP BY 1, 2\n"
            "ORDER BY 1"
        ),
    )

    ds_details = Dataset(
        display_name="Trip Details",
        query=(
            "SELECT\n"
            "  tpep_pickup_datetime,\n"
            "  tpep_dropoff_datetime,\n"
            "  pickup_zip,\n"
            "  dropoff_zip,\n"
            "  fare_amount,\n"
            "  trip_distance\n"
            "FROM `samples`.`nyctaxi`.`trips`\n"
            "WHERE fare_amount > 0 AND trip_distance > 0\n"
            "LIMIT 1000"
        ),
    )

    # --- Page 1: Overview ---
    title_widget = make_text_widget(
        Position(x=0, y=0, width=6, height=1),
        "# 🚕 NYC Taxi Sales Analytics"
    )

    total_revenue = make_viz_widget(
        Position(x=0, y=1, width=2, height=2),
        ds_trips,
        CounterSpec("Total Revenue", "total_revenue", "Total Revenue"),
        [Field("SUM(`total_revenue`)", "total_revenue")],
    )

    total_trips = make_viz_widget(
        Position(x=2, y=1, width=2, height=2),
        ds_trips,
        CounterSpec("Total Trips", "total_trips", "Total Trips"),
        [Field("SUM(`total_trips`)", "total_trips")],
    )

    avg_fare = make_viz_widget(
        Position(x=4, y=1, width=2, height=2),
        ds_trips,
        CounterSpec("Avg Fare", "avg_fare", "Average Fare"),
        [Field("AVG(`avg_fare`)", "avg_fare")],
    )

    revenue_by_month = make_viz_widget(
        Position(x=0, y=3, width=4, height=4),
        ds_trips,
        BarChartSpec(
            title="Revenue by Month",
            x=AxisEncoding("month", "Month", "temporal", "Month"),
            y=AxisEncoding("total_revenue", "Total Revenue", "quantitative", "Revenue ($)"),
        ),
        [
            Field("`month`", "month"),
            Field("SUM(`total_revenue`)", "total_revenue"),
        ],
    )

    trips_by_zip = make_viz_widget(
        Position(x=4, y=3, width=2, height=4),
        ds_trips,
        BarChartSpec(
            title="Trips by Pickup Zip",
            x=AxisEncoding("pickup_zip", "Zip Code", "categorical", "Pickup Zip"),
            y=AxisEncoding("total_trips", "Trips", "quantitative", "Number of Trips"),
        ),
        [
            Field("`pickup_zip`", "pickup_zip"),
            Field("SUM(`total_trips`)", "total_trips"),
        ],
    )

    trip_table = make_viz_widget(
        Position(x=0, y=7, width=6, height=5),
        ds_details,
        TableSpec(
            title="Trip Details",
            columns=[
                TableColumn("tpep_pickup_datetime", "Pickup", "Pickup Time",
                            col_type="datetime", display_as="datetime", order=100000),
                TableColumn("pickup_zip", "From", "Pickup Zip",
                            col_type="integer", display_as="number", order=100001,
                            number_format="0"),
                TableColumn("dropoff_zip", "To", "Dropoff Zip",
                            col_type="integer", display_as="number", order=100002,
                            number_format="0"),
                TableColumn("fare_amount", "Fare", "Fare ($)",
                            col_type="float", display_as="number", align="right",
                            order=100003, number_format="$0.00",
                            cell_format={
                                "default": {"foregroundColor": "#1FA873"},
                                "rules": [
                                    {
                                        "if": {"column": "Fare ($)", "fn": "<", "literal": "10"},
                                        "value": {"foregroundColor": "#9C2638"},
                                    },
                                    {
                                        "if": {"column": "Fare ($)", "fn": "<", "literal": "25"},
                                        "value": {"foregroundColor": "#FFD465"},
                                    },
                                ],
                            }),
                TableColumn("trip_distance", "Distance", "Distance (mi)",
                            col_type="float", display_as="number", align="right",
                            order=100004, number_format="0.0"),
            ],
            items_per_page=25,
            condensed=True,
        ),
        [
            Field("`tpep_pickup_datetime`", "tpep_pickup_datetime"),
            Field("`pickup_zip`", "pickup_zip"),
            Field("`dropoff_zip`", "dropoff_zip"),
            Field("`fare_amount`", "fare_amount"),
            Field("`trip_distance`", "trip_distance"),
        ],
        disaggregated=True,
    )

    overview_page = Page(
        display_name="Sales Overview",
        widgets=[title_widget, total_revenue, total_trips, avg_fare,
                 revenue_by_month, trips_by_zip, trip_table],
    )

    return LakeviewDashboard(
        datasets=[ds_trips, ds_details],
        pages=[overview_page],
    )


# =============================================================================
# SECTION 4: API Client — Create, Publish, Manage via REST
# =============================================================================

class LakeviewAPIClient:
    """REST API client for Databricks Lakeview operations. [Verified endpoints]"""

    def __init__(self, host: str, token: str):
        self.host = host.rstrip("/")
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _url(self, path: str) -> str:
        return f"{self.host}{path}"

    def _check(self, resp: requests.Response) -> dict:
        if resp.status_code >= 400:
            print(f"[ERROR] {resp.status_code}: {resp.text}", file=sys.stderr)
            resp.raise_for_status()
        return resp.json() if resp.text else {}

    # --- Dashboard CRUD [Verified] ---

    def create_dashboard(self, display_name: str, serialized_dashboard: str,
                         warehouse_id: str, parent_path: str = "/Shared",
                         dataset_catalog: Optional[str] = None,
                         dataset_schema: Optional[str] = None) -> dict:
        """POST /api/2.0/lakeview/dashboards"""
        params = {}
        if dataset_catalog:
            params["dataset_catalog"] = dataset_catalog
        if dataset_schema:
            params["dataset_schema"] = dataset_schema
        body = {
            "display_name": display_name,
            "serialized_dashboard": serialized_dashboard,
            "warehouse_id": warehouse_id,
            "parent_path": parent_path,
        }
        resp = self.session.post(
            self._url("/api/2.0/lakeview/dashboards"),
            params=params, json=body,
        )
        return self._check(resp)

    def get_dashboard(self, dashboard_id: str) -> dict:
        """GET /api/2.0/lakeview/dashboards/{dashboard_id}"""
        resp = self.session.get(self._url(f"/api/2.0/lakeview/dashboards/{dashboard_id}"))
        return self._check(resp)

    def update_dashboard(self, dashboard_id: str, serialized_dashboard: Optional[str] = None,
                         display_name: Optional[str] = None, warehouse_id: Optional[str] = None,
                         etag: Optional[str] = None) -> dict:
        """PATCH /api/2.0/lakeview/dashboards/{dashboard_id}"""
        body: dict = {}
        if serialized_dashboard:
            body["serialized_dashboard"] = serialized_dashboard
        if display_name:
            body["display_name"] = display_name
        if warehouse_id:
            body["warehouse_id"] = warehouse_id
        if etag:
            body["etag"] = etag
        resp = self.session.patch(
            self._url(f"/api/2.0/lakeview/dashboards/{dashboard_id}"),
            json=body,
        )
        return self._check(resp)

    def trash_dashboard(self, dashboard_id: str) -> dict:
        """DELETE /api/2.0/lakeview/dashboards/{dashboard_id}"""
        resp = self.session.delete(self._url(f"/api/2.0/lakeview/dashboards/{dashboard_id}"))
        return self._check(resp)

    def list_dashboards(self, page_size: int = 100, page_token: Optional[str] = None) -> dict:
        """GET /api/2.0/lakeview/dashboards"""
        params: dict = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        resp = self.session.get(self._url("/api/2.0/lakeview/dashboards"), params=params)
        return self._check(resp)

    # --- Publishing [Verified] ---

    def publish_dashboard(self, dashboard_id: str, embed_credentials: bool = True,
                          warehouse_id: Optional[str] = None) -> dict:
        """POST /api/2.0/lakeview/dashboards/{dashboard_id}/published"""
        body: dict = {"embed_credentials": embed_credentials}
        if warehouse_id:
            body["warehouse_id"] = warehouse_id
        resp = self.session.post(
            self._url(f"/api/2.0/lakeview/dashboards/{dashboard_id}/published"),
            json=body,
        )
        return self._check(resp)

    def get_published_dashboard(self, dashboard_id: str) -> dict:
        """GET /api/2.0/lakeview/dashboards/{dashboard_id}/published"""
        resp = self.session.get(
            self._url(f"/api/2.0/lakeview/dashboards/{dashboard_id}/published"))
        return self._check(resp)

    def unpublish_dashboard(self, dashboard_id: str) -> dict:
        """DELETE /api/2.0/lakeview/dashboards/{dashboard_id}/published"""
        resp = self.session.delete(
            self._url(f"/api/2.0/lakeview/dashboards/{dashboard_id}/published"))
        return self._check(resp)

    # --- Lifecycle [Verified] ---

    def revert_dashboard(self, dashboard_id: str) -> dict:
        """POST /api/2.0/lakeview/dashboards/{dashboard_id}/revert"""
        resp = self.session.post(
            self._url(f"/api/2.0/lakeview/dashboards/{dashboard_id}/revert"))
        return self._check(resp)

    def migrate_legacy(self, source_dashboard_id: str) -> dict:
        """POST /api/2.0/lakeview/dashboards/migrate"""
        resp = self.session.post(
            self._url("/api/2.0/lakeview/dashboards/migrate"),
            json={"source_dashboard_id": source_dashboard_id},
        )
        return self._check(resp)

    # --- Scheduling [Verified] ---

    def create_schedule(self, dashboard_id: str, cron_expression: str,
                        timezone: str = "UTC") -> dict:
        """POST /api/2.0/lakeview/dashboards/{dashboard_id}/schedules"""
        body = {
            "schedule": {
                "cron_schedule": {
                    "quartz_cron_expression": cron_expression,
                    "timezone_id": timezone,
                }
            }
        }
        resp = self.session.post(
            self._url(f"/api/2.0/lakeview/dashboards/{dashboard_id}/schedules"),
            json=body,
        )
        return self._check(resp)

    # --- Clone helper ---

    def clone_dashboard(self, source_id: str, new_name: str,
                        warehouse_id: str, parent_path: str = "/Shared") -> dict:
        """Clone a dashboard by fetching its definition and creating a new one."""
        source = self.get_dashboard(source_id)
        return self.create_dashboard(
            display_name=new_name,
            serialized_dashboard=source["serialized_dashboard"],
            warehouse_id=warehouse_id,
            parent_path=parent_path,
        )


# =============================================================================
# SECTION 5: SDK Client — Using databricks-sdk (Alternative)
# =============================================================================

def create_with_sdk(warehouse_id: str, display_name: str = "Sales Analytics Dashboard"):
    """Create and publish a dashboard using the official Databricks Python SDK."""
    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.service.dashboards import Dashboard
    except ImportError:
        print("[ERROR] databricks-sdk not installed. Run: pip install databricks-sdk")
        return

    w = WorkspaceClient()

    # Build dashboard
    dashboard_builder = build_sales_dashboard()
    serialized = dashboard_builder.to_serialized()

    # Create
    print("[INFO] Creating dashboard via SDK...")
    result = w.lakeview.create(
        dashboard=Dashboard(
            display_name=display_name,
            serialized_dashboard=serialized,
            warehouse_id=warehouse_id,
        )
    )
    print(f"[OK] Dashboard created: {result.dashboard_id}")
    print(f"     Path: {result.path}")

    # Publish
    print("[INFO] Publishing dashboard...")
    w.lakeview.publish(
        dashboard_id=result.dashboard_id,
        embed_credentials=True,
        warehouse_id=warehouse_id,
    )
    print(f"[OK] Dashboard published!")
    print(f"     View at: {os.environ.get('DATABRICKS_HOST', '')}/dashboardsv3/{result.dashboard_id}/published")

    return result


# =============================================================================
# SECTION 6: Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Create a Databricks Lakeview (AI/BI) Dashboard programmatically"
    )
    parser.add_argument("--mode", choices=["sdk", "rest", "local"], default="local",
                        help="'sdk' uses databricks-sdk, 'rest' uses raw REST API, "
                             "'local' just generates the .lvdash.json file")
    parser.add_argument("--warehouse-id", default="",
                        help="SQL Warehouse ID (required for sdk/rest modes)")
    parser.add_argument("--host", default=os.environ.get("DATABRICKS_HOST", ""),
                        help="Databricks workspace URL (for rest mode)")
    parser.add_argument("--token", default=os.environ.get("DATABRICKS_TOKEN", ""),
                        help="Databricks PAT (for rest mode)")
    parser.add_argument("--name", default="Sales Analytics Dashboard",
                        help="Dashboard display name")
    parser.add_argument("--output", default="sales_dashboard.lvdash.json",
                        help="Output file path for local mode")
    parser.add_argument("--parent-path", default="/Shared",
                        help="Workspace folder for the dashboard")
    args = parser.parse_args()

    # Build the dashboard
    dashboard = build_sales_dashboard()

    if args.mode == "local":
        # Just save the JSON file
        dashboard.save_to_file(args.output)
        print(f"\n[INFO] To deploy this dashboard:")
        print(f"  1. Via CLI:       databricks lakeview create --json '{{\"display_name\": \"{args.name}\", "
              f"\"serialized_dashboard\": \"...\", \"warehouse_id\": \"<id>\"}}'")
        print(f"  2. Via Terraform: Use databricks_dashboard resource with file_path = \"{args.output}\"")
        print(f"  3. Via Bundle:    Add to databricks.yml under resources.dashboards")

    elif args.mode == "sdk":
        if not args.warehouse_id:
            print("[ERROR] --warehouse-id is required for SDK mode", file=sys.stderr)
            sys.exit(1)
        create_with_sdk(args.warehouse_id, args.name)

    elif args.mode == "rest":
        if not args.host or not args.token:
            print("[ERROR] --host and --token are required for REST mode", file=sys.stderr)
            sys.exit(1)
        if not args.warehouse_id:
            print("[ERROR] --warehouse-id is required for REST mode", file=sys.stderr)
            sys.exit(1)

        client = LakeviewAPIClient(args.host, args.token)

        # Create
        print("[INFO] Creating dashboard via REST API...")
        result = client.create_dashboard(
            display_name=args.name,
            serialized_dashboard=dashboard.to_serialized(),
            warehouse_id=args.warehouse_id,
            parent_path=args.parent_path,
        )
        dashboard_id = result["dashboard_id"]
        print(f"[OK] Dashboard created: {dashboard_id}")

        # Publish
        print("[INFO] Publishing dashboard...")
        client.publish_dashboard(dashboard_id, embed_credentials=True,
                                 warehouse_id=args.warehouse_id)
        print(f"[OK] Dashboard published!")
        print(f"     View at: {args.host}/dashboardsv3/{dashboard_id}/published")


if __name__ == "__main__":
    main()
