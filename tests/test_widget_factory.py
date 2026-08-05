"""
test_widget_factory.py — Automated Tests for Version 3 Widget Schema Factory
=============================================================================
Tests that all widget types (Bar, Pie, Line, Scatter, Table, Counter, Filter)
generate Version 3 compliant renderSpec JSON without legacy features, blank placeholders,
or corrupted encodings.
"""

import pytest
import json
from app.services.generator.widget_factory import WidgetFactory, validate_widget_spec
from app.models.lakeview_model import LakeviewDashboard, Dataset, Page, Widget, LayoutItem, Position, generate_lakeview_id
from app.services.validator.validation_engine import validate_lakeview_dashboard


class TestBarChartWidget:
    def test_bar_chart_creation_v3(self):
        w = WidgetFactory.create_bar_widget(
            dataset_name="ds1",
            x_field="StateName",
            y_field="Total_Claim",
            title="State Claims",
            color_field="Demographics_Gender"
        )
        spec = w.spec
        assert spec["version"] == 3
        assert spec["widgetType"] == "bar"

        enc = spec["encodings"]
        assert enc["x"]["fieldName"] == "StateName"
        assert enc["x"]["scale"]["type"] == "categorical"
        assert enc["y"]["fieldName"] == "Total_Claim"
        assert enc["y"]["scale"]["type"] == "quantitative"
        assert enc["color"]["fieldName"] == "Demographics_Gender"
        assert enc["color"]["scale"]["type"] == "categorical"

        # Verify query fields
        q = w.queries[0].query
        assert q["datasetName"] == "ds1"
        assert not q["disaggregated"]
        names = [f["name"] for f in q["fields"]]
        assert "StateName" in names
        assert "Total_Claim" in names
        assert "Demographics_Gender" in names

        # Validate with factory validator
        valid, errors = validate_widget_spec(spec)
        assert valid, f"Widget spec validation failed: {errors}"


class TestPieChartWidget:
    def test_pie_chart_uses_angle_and_color_no_x_y(self):
        w = WidgetFactory.create_pie_widget(
            dataset_name="ds1",
            category_field="Demographics_Gender",
            value_field="Total_Incidents",
            title="Gender Distribution"
        )
        spec = w.spec
        assert spec["version"] == 3
        assert spec["widgetType"] == "pie"

        enc = spec["encodings"]
        # MUST contain angle and color, MUST NOT contain x or y
        assert "angle" in enc
        assert "color" in enc
        assert "x" not in enc
        assert "y" not in enc

        assert enc["color"]["fieldName"] == "Demographics_Gender"
        assert enc["color"]["scale"]["type"] == "categorical"
        assert enc["angle"]["fieldName"] == "Total_Incidents"
        assert enc["angle"]["scale"]["type"] == "quantitative"

        valid, errors = validate_widget_spec(spec)
        assert valid, f"Pie widget spec validation failed: {errors}"


class TestLineChartWidget:
    def test_line_chart_v3(self):
        w = WidgetFactory.create_line_widget(
            dataset_name="ds1",
            x_field="Date",
            y_field="Total_Payout",
            title="Payout Trend",
            is_area=False
        )
        spec = w.spec
        assert spec["version"] == 3
        assert spec["widgetType"] == "line"

        enc = spec["encodings"]
        assert enc["x"]["fieldName"] == "Date"
        assert enc["x"]["scale"]["type"] == "temporal"
        assert enc["y"]["fieldName"] == "Total_Payout"
        assert enc["y"]["scale"]["type"] == "quantitative"

        valid, errors = validate_widget_spec(spec)
        assert valid, f"Line widget spec validation failed: {errors}"


class TestScatterWidget:
    def test_scatter_widget_v3(self):
        w = WidgetFactory.create_scatter_widget(
            dataset_name="ds1",
            x_field="INCID",
            y_field="Total_Payout",
            title="Incidents vs Payout"
        )
        spec = w.spec
        assert spec["version"] == 3
        assert spec["widgetType"] == "scatter"

        enc = spec["encodings"]
        assert enc["x"]["fieldName"] == "INCID"
        assert enc["x"]["scale"]["type"] == "quantitative"
        assert enc["y"]["fieldName"] == "Total_Payout"
        assert enc["y"]["scale"]["type"] == "quantitative"

        valid, errors = validate_widget_spec(spec)
        assert valid, f"Scatter widget spec validation failed: {errors}"


class TestTableWidget:
    def test_table_widget_v1(self):
        w = WidgetFactory.create_table_widget(
            dataset_name="ds1",
            column_fields=["INCID", "INSID", "StateName", "Total_Claim"],
            title="Claims Detail Table"
        )
        spec = w.spec
        assert spec["version"] == 1
        assert spec["widgetType"] == "table"

        cols = spec["encodings"]["columns"]
        assert len(cols) == 4
        col_names = [c["fieldName"] for c in cols]
        assert col_names == ["INCID", "INSID", "StateName", "Total_Claim"]

        valid, errors = validate_widget_spec(spec)
        assert valid, f"Table widget spec validation failed: {errors}"

        q = w.queries[0].query
        assert q["disaggregated"] is True
        assert q["disaggregatedData"] is True


class TestPivotWidget:
    def test_pivot_widget_v3_with_cube_grouping(self):
        w = WidgetFactory.create_pivot_widget(
            dataset_name="ds1",
            row_fields=["Metric"],
            column_fields=["Region"],
            cell_field="sum(Value)",
            title="Region - Claim Ratio",
            query_fields=[
                {"expression": "`Region`", "name": "Region"},
                {"expression": "`Metric`", "name": "Metric"},
                {"expression": "SUM(`Value`)", "name": "sum(Value)"},
            ],
        )
        spec = w.spec
        assert spec["version"] == 3
        assert spec["widgetType"] == "pivot"
        assert spec["encodings"]["rows"][0]["fieldName"] == "Metric"
        assert spec["encodings"]["columns"][0]["fieldName"] == "Region"
        assert spec["encodings"]["cell"]["fieldName"] == "sum(Value)"

        q = w.queries[0].query
        assert q["disaggregated"] is False
        assert q["cubeGroupingSets"]["sets"] == [
            {"fieldNames": ["Metric"]},
            {"fieldNames": ["Region"]},
        ]
        assert q["orders"] == [
            {"direction": "ASC", "expression": "`Metric`"},
            {"direction": "ASC", "expression": "`Region`"},
        ]

        valid, errors = validate_widget_spec(spec)
        assert valid, f"Pivot widget spec validation failed: {errors}"

        # Table stays v1; pivot must NOT accept v1
        bad = dict(spec)
        bad["version"] = 1
        ok, errs = validate_widget_spec(bad)
        assert not ok
        assert any("version 3" in e for e in errs)


class TestSQLAggregationValidation:
    def test_missing_aggregation_rejection(self):
        """Query with non-aggregated column missing from GROUP BY should fail validation."""
        dash = LakeviewDashboard(
            datasets=[
                Dataset(
                    name="ds1",
                    displayName="ds1",
                    query="SELECT Region, StateName, SUM(Total_Claim) FROM sheet1 GROUP BY 1"
                )
            ],
            pages=[Page(name="p1", displayName="P1")]
        )
        val = validate_lakeview_dashboard(dash)
        assert not val["valid"]
        assert any("MISSING_AGGREGATION" in e or "not in GROUP BY" in e for e in val["errors"])

    def test_valid_aggregation_passes(self):
        """Query with all non-aggregated columns in GROUP BY should pass validation."""
        dash = LakeviewDashboard(
            datasets=[
                Dataset(
                    name=generate_lakeview_id(),
                    displayName="ds1",
                    query="SELECT Region, StateName, SUM(Total_Claim) AS Total_Claim FROM catalog.schema.sheet1 GROUP BY 1, 2"
                )
            ],
            pages=[Page(name=generate_lakeview_id(), displayName="P1")]
        )
        val = validate_lakeview_dashboard(dash)
        assert val["valid"], f"Validation failed: {val['errors']}"


class TestDashboardSerialization:
    def test_full_dashboard_serialization_v3(self):
        ds_id = generate_lakeview_id()
        page_id = generate_lakeview_id()
        ds = Dataset(
            name=ds_id,
            displayName="Claims Data",
            query="SELECT Demographics_Gender, SUM(Total_Incidents) AS Total_Incidents FROM sheet1 GROUP BY 1"
        )
        w_pie = WidgetFactory.create_pie_widget(
            dataset_name=ds_id,
            category_field="Demographics_Gender",
            value_field="Total_Incidents",
            title="Gender Distribution"
        )
        dash = LakeviewDashboard(
            datasets=[ds],
            pages=[
                Page(
                    name=page_id,
                    displayName="Claims",
                    layout=[
                        LayoutItem(
                            widget=w_pie,
                            position=Position(x=0, y=0, width=3, height=4)
                        )
                    ]
                )
            ]
        )
        val = validate_lakeview_dashboard(dash)
        assert val["valid"], f"Dashboard validation failed: {val['errors']}"

        json_str = dash.to_serialized()
        data = json.loads(json_str)

        assert len(data["pages"]) == 1
        spec = data["pages"][0]["layout"][0]["widget"]["spec"]
        assert spec["version"] == 3
        assert spec["widgetType"] == "pie"
        assert "angle" in spec["encodings"]
        assert "color" in spec["encodings"]
