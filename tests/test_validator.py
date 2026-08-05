import unittest
from app.services.validator.validation_engine import (
    _unaggregated_columns,
    prune_incomplete_widgets,
    validate_lakeview_dashboard,
)
from app.models.lakeview_model import LakeviewDashboard, Dataset, Page, Widget, Position, LayoutItem, WidgetQuery


class TestValidator(unittest.TestCase):
    def setUp(self):
        widget = Widget(
            name="a1b2c3d4",
            queries=[
                WidgetQuery(
                    name="main_query",
                    query={
                        "datasetName": "a1b2c3d5",
                        "fields": [
                            {"expression": "`Order_Date`", "name": "Order_Date"},
                            {"expression": "SUM(`Sales`)", "name": "Sales"},
                        ],
                        "disaggregated": False,
                    },
                )
            ],
            spec={
                "version": 3,
                "widgetType": "line",
                "encodings": {
                    "x": {
                        "fieldName": "Order_Date",
                        "displayName": "Order Date",
                        "scale": {"type": "temporal"},
                    },
                    "y": {
                        "fieldName": "Sales",
                        "displayName": "Sales",
                        "scale": {"type": "quantitative"},
                    },
                },
                "frame": {"title": "Sales Trend", "showTitle": True},
            },
        )
        self.sample_lakeview_dashboard = LakeviewDashboard(
            datasets=[Dataset(name="a1b2c3d5", displayName="Sales", query="SELECT `Order_Date` AS `Order_Date`, SUM(`Sales`) AS `Sales` FROM orders GROUP BY 1")],
            pages=[
                Page(
                    name="a1b2c3d6",
                    displayName="Overview",
                    layout=[
                        LayoutItem(
                            widget=widget,
                            position=Position(x=0, y=0, width=6, height=4)
                        )
                    ]
                )
            ]
        )

    def test_valid_dashboard(self):
        res = validate_lakeview_dashboard(self.sample_lakeview_dashboard)
        # Print any errors for debugging if this fails
        if not res["valid"]:
            print(f"Validation errors: {res['errors']}")
            print(f"Validation warnings: {res['warnings']}")
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["errors"]), 0)

    def test_invalid_layout_bounds(self):
        widget = Widget(
            name="b2c3d4e5",
            queries=[
                WidgetQuery.from_dataset(
                    "b2c3d4e6",
                    fields=[{"name": "col", "expression": "`col`"}],
                )
            ],
            spec={
                "version": 1,
                "widgetType": "table",
                "encodings": {
                    "columns": [
                        {"fieldName": "col", "type": "string", "displayAs": "string"},
                    ]
                },
            },
        )
        dash = LakeviewDashboard(
            datasets=[Dataset(name="b2c3d4e6", displayName="DS", query="SELECT 1")],
            pages=[
                Page(
                    name="b2c3d4e7",
                    displayName="Page 1",
                    layout=[
                        LayoutItem(
                            widget=widget,
                            position=Position(x=4, y=0, width=4, height=4)  # 4 + 4 = 8 > 6 bounds violation!
                        )
                    ]
                )
            ]
        )
        res = validate_lakeview_dashboard(dash)
        self.assertFalse(res["valid"])
        self.assertTrue(any("boundary" in e for e in res["errors"]))

    def test_reference_integrity_failure(self):
        widget = Widget(
            name="c3d4e5f6",
            queries=[
                WidgetQuery.from_dataset(
                    "nonexistent_ds",
                    fields=[
                        {"name": "State", "expression": "`State`"},
                        {"name": "Claims", "expression": "SUM(`Claims`)"},
                    ],
                    disaggregated=False,
                )
            ],
            spec={
                "version": 3,
                "widgetType": "bar",
                "encodings": {
                    "x": {
                        "fieldName": "State",
                        "displayName": "State",
                        "scale": {"type": "categorical"},
                    },
                    "y": {
                        "fieldName": "Claims",
                        "displayName": "Claims",
                        "scale": {"type": "quantitative"},
                    },
                },
                "frame": {"title": "Bad Ref", "showTitle": True},
            },
        )
        dash = LakeviewDashboard(
            datasets=[Dataset(name="c3d4e5f7", displayName="DS", query="SELECT 1")],
            pages=[
                Page(
                    name="c3d4e5f8",
                    displayName="Page 1",
                    layout=[
                        LayoutItem(
                            widget=widget,
                            position=Position(x=0, y=0, width=6, height=4)
                        )
                    ]
                )
            ]
        )
        res = validate_lakeview_dashboard(dash)
        self.assertFalse(res["valid"])
        self.assertTrue(any("non-existent" in e for e in res["errors"]))


UNPIVOT_SQL = (
    "SELECT `Region`, 'Total Claim' AS `Metric`, "
    "CAST(SUM(`Total_Claim`) AS DOUBLE) AS `Value` "
    "FROM hive_metastore.default.claims GROUP BY 1 UNION ALL "
    "SELECT `Region`, 'Total Paid' AS `Metric`, "
    "CAST(SUM(`Total_Paid`) AS DOUBLE) AS `Value` "
    "FROM hive_metastore.default.claims GROUP BY 1 ORDER BY 1"
)


def _pivot_dashboard():
    widget = Widget(
        name="941b452e",
        queries=[
            WidgetQuery(
                name="main_query",
                query={
                    "datasetName": "803d938b",
                    "disaggregated": False,
                    "fields": [
                        {"expression": "`Region`", "name": "Region"},
                        {"expression": "`Metric`", "name": "Metric"},
                        {"expression": "SUM(`Value`)", "name": "sum(Value)"},
                    ],
                },
            )
        ],
        spec={
            "version": 3,
            "widgetType": "pivot",
            "encodings": {
                "rows": [{"fieldName": "Metric", "scale": {"type": "categorical"}}],
                "columns": [{"fieldName": "Region", "scale": {"type": "categorical"}}],
                "cell": {"type": "single-cell", "fieldName": "sum(Value)"},
            },
            "frame": {"title": "Region - Claim Ratio", "showTitle": True},
            "data": {"queryName": "main_query"},
        },
    )
    text = Widget(
        name="fa470f37",
        multiline_textbox_spec={"lines": ["# **Insurance Claims Dashboard**"]},
    )
    return LakeviewDashboard(
        datasets=[
            Dataset(name="803d938b", displayName="Region___Claim_Ratio", query=UNPIVOT_SQL)
        ],
        pages=[
            Page(
                name="268dc45e",
                displayName="Insurance Claims Performance",
                layout=[
                    LayoutItem(widget=text, position=Position(x=0, y=0, width=6, height=2)),
                    LayoutItem(widget=widget, position=Position(x=0, y=2, width=6, height=3)),
                ],
            )
        ],
    )


class TestMultilineTextboxWidgets(unittest.TestCase):
    def test_multiline_textbox_is_valid_and_survives_pruning(self):
        dash = _pivot_dashboard()
        res = validate_lakeview_dashboard(dash)
        self.assertTrue(res["valid"], res["errors"])
        self.assertFalse(any("must have either spec" in e for e in res["errors"]))
        self.assertFalse(any("Schema Validation Error" in e for e in res["errors"]))

        removed = prune_incomplete_widgets(dash)
        self.assertEqual(removed, [])
        kept = [item.widget.name for item in dash.pages[0].layout]
        self.assertIn("fa470f37", kept)

    def test_text_content_exposes_markdown(self):
        w = Widget(name="fa470f37", multiline_textbox_spec={"lines": ["# A", "B"]})
        self.assertTrue(w.is_text_widget)
        self.assertEqual(w.text_content, "# A\nB")


class TestUnionAllAggregation(unittest.TestCase):
    def test_union_all_unpivot_has_no_missing_aggregation(self):
        self.assertEqual(_unaggregated_columns(UNPIVOT_SQL), [])

    def test_literal_projection_is_not_a_column(self):
        sql = "SELECT 'Total Claim' AS `Metric`, SUM(`v`) AS `Value` FROM t GROUP BY 1"
        self.assertEqual(_unaggregated_columns(sql), [])

    def test_missing_group_by_column_still_detected(self):
        sql = "SELECT Region, StateName, SUM(Total_Claim) FROM t GROUP BY 1"
        self.assertEqual(_unaggregated_columns(sql), ["StateName"])

    def test_offender_detected_in_second_union_branch(self):
        sql = (
            "SELECT `a`, SUM(`v`) AS `v` FROM t GROUP BY 1 UNION ALL "
            "SELECT `a`, `b`, SUM(`v`) AS `v` FROM t GROUP BY 1"
        )
        self.assertEqual(_unaggregated_columns(sql), ["b"])

    def test_function_arg_commas_do_not_shift_ordinals(self):
        sql = "SELECT COALESCE(`a`, `b`), SUM(`v`) AS `v` FROM t GROUP BY COALESCE(`a`, `b`)"
        self.assertEqual(_unaggregated_columns(sql), [])


class TestDerivedAliasBinding(unittest.TestCase):
    def test_aggregate_alias_over_dataset_column_is_not_errored(self):
        res = validate_lakeview_dashboard(_pivot_dashboard())
        self.assertFalse(
            any("sum(Value)" in e for e in res["errors"]), res["errors"]
        )
        self.assertFalse(
            any("sum(Value)" in w for w in res["warnings"]), res["warnings"]
        )

    def test_unknown_column_in_expression_is_errored(self):
        dash = _pivot_dashboard()
        fields = dash.pages[0].layout[1].widget.queries[0].query["fields"]
        fields[2] = {"expression": "SUM(`Nope`)", "name": "sum(Nope)"}
        res = validate_lakeview_dashboard(dash)
        self.assertTrue(
            any("sum(Nope)" in e for e in res["errors"]), res["errors"]
        )
        self.assertFalse(res["valid"])

    def test_wide_fields_against_unpivot_projection_are_errored(self):
        """Half-applied unpivot: dataset has Metric/Value but widget still asks for Total_*."""
        from app.services.validator.validation_engine import _projected_output_columns

        outs = _projected_output_columns(UNPIVOT_SQL)
        self.assertEqual(outs, {"Region", "Metric", "Value"})
        self.assertNotIn("Total_Claim", outs)
        self.assertNotIn("Total_Paid", outs)

        dash = _pivot_dashboard()
        # Replace Metric/Value bindings with wide-format field names that no longer exist
        q = dash.pages[0].layout[1].widget.queries[0].query
        q["fields"] = [
            {"expression": "`Region`", "name": "Region"},
            {"expression": "SUM(`Total_Incidents`)", "name": "Total_Incidents"},
            {"expression": "SUM(`Total_Claim`)", "name": "Total_Claim"},
        ]
        res = validate_lakeview_dashboard(dash)
        self.assertFalse(res["valid"], res["errors"])
        self.assertTrue(
            any("Total_Incidents" in e and "output columns" in e for e in res["errors"]),
            res["errors"],
        )
        self.assertTrue(
            any("Total_Claim" in e and "output columns" in e for e in res["errors"]),
            res["errors"],
        )


if __name__ == "__main__":
    unittest.main()
